"""What arrives from the other services.

Two kinds of handler, and the difference is the whole risk profile:

- **copy** handlers keep a read-model current. Applying one twice must produce
  the same row, because the stream is at-least-once.
- **act** handlers advance an order. Applying one twice must not advance it
  twice, and one the state machine refuses must not jam the topic forever.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app import consumer
from app.models import (
    AddressSnapshot,
    CustomerSnapshot,
    Order,
    OrderStatus,
    RestaurantSnapshot,
)


@pytest.fixture
async def placed_order(session):
    order = Order(
        customer_id=1, restaurant_id=10, address_id=5,
        status=OrderStatus.PAYMENT_PENDING.value, payment_method="CARD",
        payment_status="PENDING", subtotal=Decimal("12.00"),
        delivery_fee=Decimal("0"), total=Decimal("12.00"),
        refund_status="NONE", refund_amount=Decimal("0"),
    )
    session.add(order)
    await session.commit()
    return order


# ---- copy handlers --------------------------------------------------------


async def test_an_address_event_fills_the_read_model(session):
    await consumer._apply_address_event(session, {
        "address_id": 5, "user_id": 1, "city": "Metropolis",
        "latitude": 12.9, "longitude": 77.6,
    })
    snapshot = await session.get(AddressSnapshot, 5)
    assert snapshot.city == "Metropolis"
    assert snapshot.latitude == 12.9


async def test_applying_the_same_event_twice_is_harmless(session):
    """The property every copy handler needs, because the stream redelivers."""
    payload = {"address_id": 5, "user_id": 1, "city": "Metropolis"}
    await consumer._apply_address_event(session, payload)
    await consumer._apply_address_event(session, payload)

    rows = list(await session.scalars(select(AddressSnapshot)))
    assert len(rows) == 1


async def test_a_failed_regeocode_clears_the_old_point(session):
    """Null is assigned, not skipped: stale coordinates for a new street address
    would route a delivery to the wrong place."""
    await consumer._apply_address_event(session, {
        "address_id": 5, "user_id": 1, "city": "Metropolis",
        "latitude": 12.9, "longitude": 77.6,
    })
    await consumer._apply_address_event(session, {
        "address_id": 5, "user_id": 1, "city": "Gotham",
        "latitude": None, "longitude": None,
    })
    snapshot = await session.get(AddressSnapshot, 5)
    assert snapshot.city == "Gotham"
    assert snapshot.latitude is None


async def test_a_restaurant_event_records_the_owner(session):
    await consumer._apply_restaurant_event(session, {
        "restaurant_id": 10, "owner_id": 7, "name": "Test Kitchen",
    })
    snapshot = await session.get(RestaurantSnapshot, 10)
    assert snapshot.owner_id == 7
    assert snapshot.name == "Test Kitchen"


async def test_only_customers_are_copied(session):
    """A driver or an owner never appears on an order as the person notified."""
    await consumer._apply_user_event(session, {
        "user_id": 3, "role": "driver", "first_name": "Dev", "last_name": "Driver",
    })
    assert await session.get(CustomerSnapshot, 3) is None

    await consumer._apply_user_event(session, {
        "user_id": 4, "role": "customer", "first_name": "Cara", "last_name": "Customer",
    })
    assert (await session.get(CustomerSnapshot, 4)).display_name == "Cara C."


async def test_a_customer_copy_holds_no_contact_details(session):
    """Orders never contacts anyone. Notifications owns addresses."""
    await consumer._apply_user_event(session, {
        "user_id": 4, "role": "customer", "first_name": "Cara",
        "last_name": "Customer", "email": "cara@example.com", "phone": "+919876543210",
    })
    snapshot = await session.get(CustomerSnapshot, 4)
    assert not hasattr(snapshot, "email")
    assert not hasattr(snapshot, "phone")


# ---- act handlers ---------------------------------------------------------


async def test_a_payment_event_advances_the_order(session, placed_order):
    await consumer._apply_payment_event(session, {
        "order_id": placed_order.id, "payment_status": "SUCCEEDED",
    })
    await session.refresh(placed_order)
    assert placed_order.status == OrderStatus.PAYMENT_SUCCESS.value


async def test_a_replayed_payment_event_does_not_advance_twice(session, placed_order):
    payload = {"order_id": placed_order.id, "payment_status": "SUCCEEDED"}
    await consumer._apply_payment_event(session, payload)
    await consumer._apply_payment_event(session, payload)

    await session.refresh(placed_order)
    assert placed_order.status == OrderStatus.PAYMENT_SUCCESS.value


async def test_a_failed_payment_changes_nothing(session, placed_order):
    await consumer._apply_payment_event(session, {
        "order_id": placed_order.id, "payment_status": "FAILED",
    })
    await session.refresh(placed_order)
    assert placed_order.status == OrderStatus.PAYMENT_PENDING.value


@pytest.mark.parametrize("delivery_status,expected", [
    ("PICKED_UP", OrderStatus.OUT_FOR_DELIVERY.value),
    ("DELIVERED", OrderStatus.DELIVERED.value),
])
async def test_delivery_events_advance_the_order(
    session, placed_order, delivery_status, expected
):
    # Walk it up to where a driver could plausibly act on it.
    placed_order.status = OrderStatus.READY_FOR_PICKUP.value
    if delivery_status == "DELIVERED":
        placed_order.status = OrderStatus.OUT_FOR_DELIVERY.value
    await session.commit()

    await consumer._apply_delivery_event(session, {
        "order_id": placed_order.id, "status": delivery_status, "driver_id": 3,
    })
    await session.refresh(placed_order)
    assert placed_order.status == expected


async def test_assignment_events_change_nothing_about_the_order(session, placed_order):
    """ASSIGNED and ACCEPTED are facts about a delivery, not about an order."""
    before = placed_order.status
    for status in ("ASSIGNED", "ACCEPTED"):
        await consumer._apply_delivery_event(session, {
            "order_id": placed_order.id, "status": status, "driver_id": 3,
        })
    await session.refresh(placed_order)
    assert placed_order.status == before


async def test_a_refused_transition_does_not_jam_the_topic(session, placed_order):
    """The state machine will not take an unpaid order straight to DELIVERED.

    That is a bad event, not a broken connection — so it is swallowed and the
    offset moves on. Redelivering it forever would stop every later event.
    """
    await consumer._apply_delivery_event(session, {
        "order_id": placed_order.id, "status": "DELIVERED", "driver_id": 3,
    })  # must not raise

    await session.refresh(placed_order)
    assert placed_order.status == OrderStatus.PAYMENT_PENDING.value


async def test_an_event_for_an_unknown_order_is_ignored(session):
    await consumer._apply_delivery_event(session, {
        "order_id": 9999, "status": "PICKED_UP", "driver_id": 3,
    })  # must not raise

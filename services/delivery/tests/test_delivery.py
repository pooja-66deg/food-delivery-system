"""Assignment, and the read-models it depends on.

Everything the monolith read by joining — the restaurant's coordinates, the
customer's address, the driver roster — is a local copy here. So these tests are
mostly about what happens with a copy that is partial, empty, or absent, which
is the normal state of a read-model rather than an edge case.
"""

import pytest
from sqlalchemy import select

from app import consumer, service
from app.models import Delivery, DeliveryStatus, Driver, OrderSnapshot


@pytest.fixture
async def roster(session):
    """Two active drivers, one deactivated."""
    for driver_id, active in ((1, True), (2, True), (3, False)):
        await consumer._apply_user_event(session, {
            "user_id": driver_id, "role": "driver", "first_name": f"D{driver_id}",
            "last_name": "River", "is_active": active,
        })
    return session


async def test_only_drivers_are_copied(session):
    """A read-model copies what its owner uses, not what the source happens to
    have — otherwise every service ends up holding personal data."""
    await consumer._apply_user_event(session, {
        "user_id": 9, "role": "customer", "first_name": "Cara", "last_name": "Customer",
    })
    assert list(await session.scalars(select(Driver))) == []


async def test_available_drivers_excludes_the_deactivated(session, roster):
    available = await service.list_available_drivers(session)
    assert sorted(d.id for d in available) == [1, 2]


async def test_a_driver_on_an_active_delivery_is_not_available(session, roster):
    session.add(Delivery(order_id=1, driver_id=1, status=DeliveryStatus.ACCEPTED.value))
    await session.commit()

    available = await service.list_available_drivers(session)
    assert [d.id for d in available] == [2]


async def test_an_unassigned_delivery_does_not_hide_every_driver(session, roster):
    """The bug this test exists for.

    ``driver_id`` is nullable, and the original query used
    ``User.id.notin_(subquery)``. A single NULL in that subquery makes the whole
    predicate return nothing — so one unassigned delivery reported that *no*
    driver was available, and orders silently stopped being assigned.
    """
    session.add(Delivery(order_id=1, driver_id=None, status=DeliveryStatus.UNASSIGNED.value))
    await session.commit()

    available = await service.list_available_drivers(session)
    assert sorted(d.id for d in available) == [1, 2]


async def test_assignment_is_idempotent(session, roster):
    """An at-least-once stream will deliver "ready for pickup" twice, and the
    second one must not create a second delivery or re-offer the first."""
    first = await service.assign_for_order(session, order_id=1)
    second = await service.assign_for_order(session, order_id=1)

    assert first.id == second.id
    assert len(list(await session.scalars(select(Delivery)))) == 1


async def test_assignment_with_no_free_driver_is_still_a_delivery(session):
    """UNASSIGNED is a real state, not a failure: the order is ready, and a
    driver will be found later."""
    delivery = await service.assign_for_order(session, order_id=1)
    assert delivery.status == DeliveryStatus.UNASSIGNED.value
    assert delivery.driver_id is None


async def test_an_order_event_fills_the_snapshot(session):
    await consumer._apply_order_event(session, {
        "order_id": 1, "customer_id": 5, "status": "PAYMENT_SUCCESS",
        "restaurant_latitude": 12.9, "restaurant_longitude": 77.6,
        "destination_latitude": 12.8, "destination_longitude": 77.5,
    })
    snapshot = await session.get(OrderSnapshot, 1)
    assert snapshot.customer_id == 5
    assert snapshot.restaurant_latitude == 12.9


async def test_ready_for_pickup_triggers_assignment(session, roster):
    await consumer._apply_order_event(session, {
        "order_id": 1, "customer_id": 5, "status": "READY_FOR_PICKUP",
    })
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == 1))
    assert delivery is not None
    assert delivery.driver_id in (1, 2)


async def test_coordinates_are_not_erased_by_a_thinner_event(session):
    """A later event without coordinates must not blank what an earlier one knew,
    or a driver loses their navigation mid-delivery."""
    await consumer._apply_order_event(session, {
        "order_id": 1, "customer_id": 5, "status": "PAYMENT_SUCCESS",
        "restaurant_latitude": 12.9, "restaurant_longitude": 77.6,
    })
    await consumer._apply_order_event(session, {
        "order_id": 1, "customer_id": 5, "status": "RESTAURANT_ACCEPTED",
    })
    snapshot = await session.get(OrderSnapshot, 1)
    assert snapshot.restaurant_latitude == 12.9


async def test_a_driver_cannot_act_on_someone_elses_delivery(session, roster):
    from fastapi import HTTPException

    await service.assign_for_order(session, order_id=1)
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == 1))
    other_driver = 2 if delivery.driver_id == 1 else 1

    with pytest.raises(HTTPException) as exc:
        await service.accept_assignment(session, other_driver, 1)
    assert exc.value.status_code == 403


async def test_status_changes_announce_themselves(session, roster):
    """Orders advances the order from these; notifications tells the driver."""
    import json

    from app.models import OutboxEvent

    await service.assign_for_order(session, order_id=1)
    events = [
        json.loads(e.payload)
        for e in await session.scalars(
            select(OutboxEvent).where(OutboxEvent.topic == "delivery-events")
        )
    ]
    assert events and events[-1]["order_id"] == 1


# ---- reassign authorization -----------------------------------------------
#
# The route's require_role("restaurant", "admin") says the caller is *a*
# restaurant, not that they own *this* one. Without the check these cover, any
# restaurant account could reassign the driver on any order on the platform —
# which is exactly what shipped, and survived the split into this service.


@pytest.fixture
async def order_for_owner(session, roster):
    """An assigned order belonging to restaurant 10, owned by user 7."""
    from app.models import RestaurantSnapshot

    await consumer._apply_restaurant_event(session, {"restaurant_id": 10, "owner_id": 7})
    await consumer._apply_order_event(session, {
        "order_id": 1, "customer_id": 5, "restaurant_id": 10, "status": "READY_FOR_PICKUP",
    })
    assert await session.get(RestaurantSnapshot, 10) is not None
    return 1


class _Caller:
    def __init__(self, user_id, role="restaurant"):
        self.user_id = user_id
        self.role = role


async def test_the_owner_may_reassign(session, order_for_owner):
    delivery = await service.reassign_delivery_for_order(
        session, _Caller(user_id=7), order_id=1, new_driver_id=2
    )
    assert delivery.driver_id == 2


async def test_another_restaurant_may_not(session, order_for_owner):
    """The hole. Caller 99 holds the restaurant role but owns nothing here."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await service.reassign_delivery_for_order(
            session, _Caller(user_id=99), order_id=1, new_driver_id=2
        )
    assert exc.value.status_code == 403


async def test_an_admin_may_reassign_anything(session, order_for_owner):
    delivery = await service.reassign_delivery_for_order(
        session, _Caller(user_id=99, role="admin"), order_id=1, new_driver_id=2
    )
    assert delivery.driver_id == 2


async def test_an_order_we_cannot_attribute_is_refused(session, roster):
    """An order whose event predates the restaurant_id column, or that we have
    never heard of. Refusing is the safe direction: the alternative is allowing
    an action we cannot justify."""
    from fastapi import HTTPException

    await consumer._apply_order_event(session, {
        "order_id": 2, "customer_id": 5, "status": "READY_FOR_PICKUP",
    })
    with pytest.raises(HTTPException) as exc:
        await service.reassign_delivery_for_order(
            session, _Caller(user_id=7), order_id=2, new_driver_id=2
        )
    assert exc.value.status_code == 404

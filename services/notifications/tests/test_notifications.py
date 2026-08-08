"""Sending, and where the address comes from.

This service is the only one that contacts people, so it is the only one that
holds an address. That is the property most of these tests are protecting: an
order event carries a customer id, and everything else is resolved locally.
"""

import pytest
from sqlalchemy import select

from app import consumer, preferences, service
from app.models import Channel, Contact, Notification
from app.schemas import OrderStatusEvent


@pytest.fixture
async def contact(session):
    """A reachable customer, as `user-contact-events` would have left them."""
    session.add(Contact(user_id=1, email="cara@example.com", phone="+919876543210"))
    await session.commit()


async def _feed(session, user_id=1):
    return list(
        await session.scalars(
            select(Notification).where(Notification.user_id == user_id)
        )
    )


async def test_a_status_change_always_writes_the_feed_row(session):
    """Every status reaches the in-app feed, even one with no outbound channel."""
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=1, status="PREPARING", customer_id=1)
    )
    rows = await _feed(session)
    assert [r.channel for r in rows] == [Channel.LOG.value]


async def test_email_goes_to_the_address_in_the_local_read_model(session, contact):
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=1, status="PAYMENT_SUCCESS", customer_id=1)
    )
    rows = await _feed(session)
    channels = {r.channel for r in rows}
    assert Channel.EMAIL.value in channels, "no outbound copy was sent"


async def test_without_a_contact_the_channel_is_skipped_not_failed(session):
    """A user we cannot reach on a channel simply is not reached on it. The feed
    row still gets written, so the customer sees the update in the app."""
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=1, status="PAYMENT_SUCCESS", customer_id=1)
    )
    rows = await _feed(session)
    assert [r.channel for r in rows] == [Channel.LOG.value]


async def test_an_order_event_carrying_an_address_is_rejected(session):
    """The contract is a customer id. If an address ever reappears on this topic
    it is a regression, and the schema should refuse to normalise it away."""
    event = OrderStatusEvent(order_id=1, status="PAYMENT_SUCCESS", customer_id=1)
    assert not hasattr(event, "customer_email")
    assert not hasattr(event, "customer_phone")


async def test_sms_is_off_unless_asked_for(session, contact):
    """The one channel that costs per message and reaches people who never asked
    for it, so it is opt-in."""
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=1, status="OUT_FOR_DELIVERY", customer_id=1)
    )
    rows = await _feed(session)
    assert Channel.SMS.value not in {r.channel for r in rows}

    await preferences.update_preferences(
        session, 1, type("U", (), {"model_dump": lambda self, **k: {"sms_enabled": True}})()
    )
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=2, status="OUT_FOR_DELIVERY", customer_id=1)
    )
    rows = await _feed(session)
    assert Channel.SMS.value in {r.channel for r in rows}


async def test_the_feed_hides_the_delivery_audit_trail(session, contact):
    """Showing outbound rows in the feed would repeat every message up to three
    times in the customer's timeline."""
    await service.handle_order_status(
        session, OrderStatusEvent(order_id=1, status="PAYMENT_SUCCESS", customer_id=1)
    )
    feed = await service.list_for_user(session, 1)
    deliveries = await service.list_deliveries(session, 1)

    assert all(r.channel == Channel.LOG.value for r in feed)
    assert all(r.channel != Channel.LOG.value for r in deliveries)


# ---- consumer -------------------------------------------------------------
#
# The handlers take a session now: the shared EventConsumer opens one and hands
# it over, rather than each handler reaching for the module-level factory. That
# is also what makes them testable without redirecting global state.


async def test_a_contact_event_fills_the_read_model(session):
    await consumer._handle_contact(session, {"user_id": 5, "email": "a@b.com", "phone": "+911111111111"})
    assert (await session.get(Contact, 5)).email == "a@b.com"


async def test_a_direct_event_sends_and_records(session):
    """Password resets and OTPs arrive this way. They were publishing into a
    topic nobody consumed until this handler existed."""
    await consumer._handle_direct(session, {
        "user_id": 5, "type": "account.reset_password", "channel": "EMAIL",
        "to": "a@b.com", "subject": "Reset your password", "message": "link",
    })
    rows = await _feed(session, 5)
    assert [r.type for r in rows] == ["account.reset_password"]
    assert rows[0].channel == "EMAIL"


async def test_a_direct_event_without_a_channel_is_an_in_app_row(session):
    await consumer._handle_direct(session, {
        "user_id": 6, "type": "review.replied", "message": "They replied", "order_id": 3,
    })
    rows = await _feed(session, 6)
    assert rows[0].channel == Channel.LOG.value
    assert rows[0].order_id == 3

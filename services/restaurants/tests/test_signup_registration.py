"""Creating a venue from a sign-up event rather than an API call.

An applicant's account is inactive until their venue is approved, so they hold
no token and cannot POST /restaurants themselves. The users service collects the
business details during registration and hands them over on a topic; this is the
other end of that.

What matters here is not that a row appears — it is that the path cannot be used
to get around the approval gate, and that redelivery does not produce a second
venue.
"""

import json

from sqlalchemy import select

from app import service
from app.models import PENDING, OutboxEvent, Restaurant

SIGNUP = {
    "owner_id": 42,
    "name": "Tiffin House",
    "city": "Surat",
    "address_line": "1 KK Road",
    "phone": "+919876500001",
    "cuisine": "Gujarati",
    "food_type": "veg",
}


async def _events(session, topic: str) -> list[dict]:
    rows = await session.scalars(
        select(OutboxEvent).where(OutboxEvent.topic == topic).order_by(OutboxEvent.id)
    )
    return [json.loads(r.payload) for r in rows]


async def test_a_signup_creates_a_pending_venue(session):
    restaurant = await service.register_from_signup(session, SIGNUP)

    assert restaurant is not None
    assert restaurant.name == "Tiffin House"
    assert restaurant.food_type == "veg"
    assert restaurant.owner_id == 42


async def test_a_signup_cannot_arrive_pre_approved(session):
    """The gate has to hold on this path too.

    The API route drops approval_status because it is absent from the payload
    schema. This path has no schema — it reads a dict off a topic — so the value
    is set explicitly rather than copied, and a forged event carrying
    "approved" gets a pending venue like everyone else.
    """
    restaurant = await service.register_from_signup(
        session, {**SIGNUP, "approval_status": "approved"}
    )
    assert restaurant.approval_status == PENDING


async def test_redelivery_does_not_create_a_second_venue(session):
    """At-least-once delivery guarantees this event arrives twice eventually."""
    first = await service.register_from_signup(session, SIGNUP)
    assert first is not None

    assert await service.register_from_signup(session, SIGNUP) is None

    rows = list(await session.scalars(select(Restaurant).where(Restaurant.owner_id == 42)))
    assert len(rows) == 1


async def test_an_unusable_payload_is_dropped_rather_than_retried(session):
    """Returning None acknowledges it. A payload with no owner will never become
    valid, and redelivering it forever would block every registration queued
    behind it on the same topic."""
    assert await service.register_from_signup(session, {"name": "No Owner"}) is None
    assert await service.register_from_signup(session, {"owner_id": 9}) is None


async def test_the_new_venue_is_announced(session):
    """Other services keep a copy — and the users service needs this event to
    learn the approval status that eventually unlocks the owner's account."""
    await service.register_from_signup(session, SIGNUP)
    [event] = await _events(session, "restaurant-events")

    assert event["owner_id"] == 42
    assert event["approval_status"] == PENDING


async def test_the_admin_is_alerted(session, monkeypatch):
    """Otherwise approval is a queue nobody is told about, and a Friday-evening
    registration sits until somebody happens to open the console."""
    monkeypatch.setattr(service.settings, "admin_alert_email", "ops@example.com")

    await service.register_from_signup(session, SIGNUP)
    [alert] = await _events(session, "notification-events")

    assert alert["to"] == "ops@example.com"
    assert alert["channel"] == "EMAIL"
    assert "Tiffin House" in alert["subject"]


async def test_no_alert_address_is_a_supported_state(session, monkeypatch):
    """The console still lists everything pending, so an unconfigured deploy is
    one where operators poll — not one that drops registrations."""
    monkeypatch.setattr(service.settings, "admin_alert_email", "")

    restaurant = await service.register_from_signup(session, SIGNUP)
    assert restaurant is not None
    assert await _events(session, "notification-events") == []


async def test_a_signup_venue_is_invisible_to_customers(client, session):
    """The point of the whole exercise: registering does not put you in front of
    a customer, whichever door you came in through."""
    await service.register_from_signup(session, SIGNUP)

    r = await client.get("/restaurants")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []

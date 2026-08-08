"""What this service tells the rest of the platform.

Users is the service everything else keeps a copy of, so its events are its most
important output — more so than any response body. Every assertion here is about
what other services will and will not receive.
"""

import json

import pytest
from sqlalchemy import select

from app.models import OutboxEvent


async def _events(session, topic: str) -> list[dict]:
    rows = await session.scalars(
        select(OutboxEvent).where(OutboxEvent.topic == topic).order_by(OutboxEvent.id)
    )
    return [json.loads(r.payload) for r in rows]


async def test_registration_publishes_on_both_topics(client, session, register_payload):
    r = await client.post("/auth/register", json=register_payload())
    assert r.status_code == 201, r.text

    assert len(await _events(session, "user-events")) == 1
    assert len(await _events(session, "user-contact-events")) == 1


async def test_the_open_topic_carries_no_contact_details(client, session, register_payload):
    """The whole reason there are two topics.

    Orders, delivery and restaurants all consume ``user-events`` for a name or a
    role. If an address rode along, each would end up storing one it never uses.
    """
    await client.post("/auth/register", json=register_payload())
    [event] = await _events(session, "user-events")

    assert event["first_name"] == "Cara"
    assert event["role"] == "customer"
    assert "email" not in event
    assert "phone" not in event


async def test_the_restricted_topic_carries_the_address(client, session, register_payload):
    await client.post("/auth/register", json=register_payload())
    [event] = await _events(session, "user-contact-events")

    assert event["email"] == "cara@example.com"
    assert event["phone"] == "+919876543210"


async def test_no_event_ever_carries_the_password_hash(client, session, register_payload):
    await client.post("/auth/register", json=register_payload())
    for topic in ("user-events", "user-contact-events"):
        for event in await _events(session, topic):
            assert "hashed_password" not in event
            assert "password" not in event


async def test_the_event_and_the_user_commit_together(client, session, register_payload):
    """The outbox's one guarantee: a rejected registration publishes nothing.

    Without it, a duplicate-email 409 could still announce a user that does not
    exist, and every consumer would hold a row for them forever.
    """
    await client.post("/auth/register", json=register_payload())
    before = len(await _events(session, "user-events"))

    duplicate = await client.post("/auth/register", json=register_payload())
    assert duplicate.status_code == 409

    assert len(await _events(session, "user-events")) == before


async def test_adding_an_address_publishes_where_not_who(client, session, register_payload):
    """Orders needs to know where an order can go, not where somebody lives."""
    await client.post("/auth/register", json=register_payload())
    token = (await client.post("/auth/login", json={
        "email": "cara@example.com", "password": "supersecret1"})).json()["access_token"]

    r = await client.post(
        "/users/me/addresses",
        json={"label": "home", "line1": "22 Elm St", "city": "Metropolis",
              "postal_code": "12345", "is_default": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text

    [event] = await _events(session, "address-events")
    assert event["city"] == "Metropolis"
    assert "line1" not in event, "the street line has no business leaving this service"
    assert "postal_code" not in event


@pytest.mark.parametrize("path,body", [
    ("/auth/forgot-password", {"email": "cara@example.com"}),
    ("/auth/otp/request", {"phone": "+919876543210"}),
])
async def test_outbound_messages_are_queued_not_sent(client, session, register_payload, path, body):
    """The monolith called SendGrid and Twilio inline, so a slow provider held up
    a signup. Now it records an event and the notifications service sends."""
    await client.post("/auth/register", json=register_payload())
    before = len(await _events(session, "notification-events"))

    r = await client.post(path, json=body)
    assert r.status_code == 200, r.text

    events = await _events(session, "notification-events")
    assert len(events) > before
    assert events[-1]["to"] in ("cara@example.com", "+919876543210")

"""Registering as a restaurant, and the approval gate on the account.

A restaurant applicant is the one role that cannot sign in the moment it signs
up. That single difference has consequences in four places, and each is a test
here:

- the sign-up payload must carry the business, because there is no later session
  in which to supply it;
- the account is created inactive, so login refuses it;
- login says *why*, which the generic "invalid email or password" cannot;
- an approval event, and only an approval event, lets them in.
"""

import json

from sqlalchemy import select

from app import service
from app.models import OutboxEvent, User

VENUE = {
    "name": "Tiffin House",
    "city": "Surat",
    "address_line": "1 KK Road",
    "phone": "+919876500001",
}


async def _events(session, topic: str) -> list[dict]:
    rows = await session.scalars(
        select(OutboxEvent).where(OutboxEvent.topic == topic).order_by(OutboxEvent.id)
    )
    return [json.loads(r.payload) for r in rows]


async def _register_owner(client, register_payload, **venue_overrides):
    return await client.post(
        "/auth/register",
        json=register_payload(
            email="owner@example.com",
            role="restaurant",
            restaurant={**VENUE, **venue_overrides},
        ),
    )


# ---------- the payload ----------

async def test_restaurant_signup_requires_the_business(client, register_payload):
    """Without this the operator would be approving a name and an email.

    It is a 422 rather than a "fill it in later" because there is no later: the
    account is inactive until approved, so the applicant cannot sign in to
    finish the job.
    """
    r = await client.post(
        "/auth/register", json=register_payload(email="o@example.com", role="restaurant")
    )
    assert r.status_code == 422, r.text


async def test_other_roles_may_not_send_a_business(client, register_payload):
    """Rejected rather than ignored. Silently dropping the field would let a
    customer believe they had registered a venue."""
    r = await client.post(
        "/auth/register", json=register_payload(role="customer", restaurant=VENUE)
    )
    assert r.status_code == 422, r.text


# ---------- the account ----------

async def test_an_applicant_is_created_inactive_and_pending(
    client, session, register_payload
):
    r = await _register_owner(client, register_payload)
    assert r.status_code == 201, r.text

    user = await session.scalar(select(User).where(User.email == "owner@example.com"))
    assert user.is_active is False
    assert user.approval_status == "pending"


async def test_a_customer_is_unaffected(client, session, register_payload):
    """The gate is for restaurants only — everyone else still signs straight in."""
    r = await client.post("/auth/register", json=register_payload())
    assert r.status_code == 201, r.text

    user = await session.scalar(select(User).where(User.email == "cara@example.com"))
    assert user.is_active is True
    assert user.approval_status is None


async def test_an_applicant_cannot_log_in(client, register_payload):
    await _register_owner(client, register_payload)
    r = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "supersecret1"}
    )
    assert r.status_code == 401, r.text


async def test_login_explains_the_wait_to_a_correct_password(client, register_payload):
    """The applicant has to be able to tell "still waiting" from "wrong password".

    Otherwise a correct password looks like a typo and they register again — and
    the second registration is the one that hits the duplicate-email conflict.
    """
    await _register_owner(client, register_payload)
    r = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "supersecret1"}
    )
    assert service.PENDING_APPROVAL_MESSAGE in r.text


async def test_a_wrong_password_still_gets_the_generic_error(client, register_payload):
    """The enumeration property that matters is unchanged: the pending state is
    disclosed only to somebody who already proved they hold the password."""
    await _register_owner(client, register_payload)
    r = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "not-the-one"}
    )
    assert r.status_code == 401
    assert service.PENDING_APPROVAL_MESSAGE not in r.text
    assert "Invalid email or password" in r.text


# ---------- handing the venue over ----------

async def test_signup_publishes_the_venue_to_restaurants(
    client, session, register_payload
):
    await _register_owner(client, register_payload)
    [event] = await _events(session, "restaurant-registrations")

    assert event["name"] == "Tiffin House"
    assert event["city"] == "Surat"
    assert event["food_type"] == "both"


async def test_business_details_stay_off_the_open_topic(
    client, session, register_payload
):
    """``user-events`` is subscribed to by everybody. A venue's street address
    and phone number have no business reaching a driver roster."""
    await _register_owner(client, register_payload)
    [event] = await _events(session, "user-events")

    assert "address_line" not in event
    assert "1 KK Road" not in json.dumps(event)


async def test_a_customer_publishes_no_registration(client, session, register_payload):
    await client.post("/auth/register", json=register_payload())
    assert await _events(session, "restaurant-registrations") == []


# ---------- the decision ----------

async def test_approval_lets_the_owner_in(client, session, register_payload):
    await _register_owner(client, register_payload)
    user = await session.scalar(select(User).where(User.email == "owner@example.com"))

    changed = await service.apply_restaurant_decision(session, user.id, "approved")
    assert changed is True

    await session.refresh(user)
    assert user.is_active is True
    assert user.approval_status == "approved"

    r = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "supersecret1"}
    )
    assert r.status_code == 200, r.text


async def test_rejection_records_the_reason_without_letting_them_in(
    client, session, register_payload
):
    await _register_owner(client, register_payload)
    user = await session.scalar(select(User).where(User.email == "owner@example.com"))

    await service.apply_restaurant_decision(session, user.id, "rejected")
    await session.refresh(user)
    assert user.is_active is False

    r = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "supersecret1"}
    )
    assert r.status_code == 401
    assert service.REJECTED_MESSAGE in r.text


async def test_a_redelivered_decision_changes_nothing(session, register_payload, client):
    """At-least-once delivery means this runs twice. The second run must not
    announce the user again, or every consumer re-processes a no-op."""
    await _register_owner(client, register_payload)
    user = await session.scalar(select(User).where(User.email == "owner@example.com"))

    assert await service.apply_restaurant_decision(session, user.id, "approved") is True
    before = len(await _events(session, "user-events"))

    assert await service.apply_restaurant_decision(session, user.id, "approved") is False
    assert len(await _events(session, "user-events")) == before


async def test_a_rejection_does_not_deactivate_a_trading_owner(
    session, register_payload, client
):
    """A rejection is a decision about a listing, not a ban on a person. By the
    time a second venue is turned down the owner may have been trading for a
    year, and taking their account away is not what an operator asked for."""
    await _register_owner(client, register_payload)
    user = await session.scalar(select(User).where(User.email == "owner@example.com"))
    await service.apply_restaurant_decision(session, user.id, "approved")

    await service.apply_restaurant_decision(session, user.id, "rejected")
    await session.refresh(user)
    assert user.is_active is True


async def test_a_decision_about_a_non_owner_is_ignored(session, client, register_payload):
    """The consumer sees every restaurant event, and an owner id that belongs to
    a customer is a mismatch this service must not act on."""
    await client.post("/auth/register", json=register_payload())
    user = await session.scalar(select(User).where(User.email == "cara@example.com"))

    assert await service.apply_restaurant_decision(session, user.id, "approved") is False
    await session.refresh(user)
    assert user.approval_status is None

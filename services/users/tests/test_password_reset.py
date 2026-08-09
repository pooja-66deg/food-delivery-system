"""Forgetting a password, and getting back in.

The only self-service route into a locked-out account — ``change-password``
needs the current one. Three properties matter more than the happy path:

- the endpoint never reveals whether an address is registered;
- a token works exactly once, and says the same thing when it does not work,
  whether it is unknown, spent, or expired;
- a successful reset evicts every existing session, because the person who
  locked the owner out must lose their access at that moment.
"""

import pytest


async def _register(client, register_payload, **overrides):
    payload = {**register_payload(), **overrides}
    r = await client.post("/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return payload


async def _reset_token(client, email):
    """Ask for a reset and return the token the dev-mode response carries."""
    r = await client.post("/auth/forgot-password", json={"email": email})
    assert r.status_code == 200, r.text
    return r.json().get("debug_token")


async def test_a_reset_token_lets_the_owner_choose_a_new_password(client, register_payload):
    user = await _register(client, register_payload)
    token = await _reset_token(client, user["email"])
    assert token

    r = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"}
    )
    assert r.status_code == 204, r.text

    signed_in = await client.post(
        "/auth/login", json={"email": user["email"], "password": "brandnewpass1"}
    )
    assert signed_in.status_code == 200, signed_in.text


async def test_the_old_password_stops_working(client, register_payload):
    user = await _register(client, register_payload)
    token = await _reset_token(client, user["email"])
    await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"}
    )

    r = await client.post(
        "/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert r.status_code == 401, r.text


async def test_an_unknown_email_answers_the_same_as_a_known_one(client, register_payload):
    """The response is an oracle if it differs. Anyone can ask, with no
    credentials, whether a given person has an account here."""
    user = await _register(client, register_payload)

    known = await client.post("/auth/forgot-password", json={"email": user["email"]})
    unknown = await client.post(
        "/auth/forgot-password", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]


async def test_no_token_is_issued_for_an_unknown_email(client):
    """Same message either way, but nothing is actually minted."""
    r = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert r.json().get("debug_token") is None


async def test_a_reset_token_works_only_once(client, register_payload):
    user = await _register(client, register_payload)
    token = await _reset_token(client, user["email"])

    first = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"}
    )
    assert first.status_code == 204

    second = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "thirdpassword1"}
    )
    assert second.status_code == 401, second.text


async def test_an_unknown_token_is_refused(client):
    r = await client.post(
        "/auth/reset-password",
        json={"token": "a" * 40, "new_password": "brandnewpass1"},
    )
    assert r.status_code == 401, r.text


async def test_a_reset_evicts_every_existing_session(client, register_payload):
    """The point of a reset, not a side effect: whoever locked the owner out
    loses their access the moment the owner takes the account back."""
    user = await _register(client, register_payload)
    tokens = (
        await client.post(
            "/auth/login", json={"email": user["email"], "password": user["password"]}
        )
    ).json()
    bearer = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/users/me", headers=bearer)).status_code == 200

    token = await _reset_token(client, user["email"])
    await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"}
    )

    # The old access token still verifies as a JWT — it is the generation claim
    # that no longer matches, which is what makes eviction possible without
    # every service calling this one on every request.
    assert (await client.get("/users/me", headers=bearer)).status_code == 401


async def test_the_reset_email_is_queued_not_sent(client, session, register_payload):
    """This service records an event; notifications delivers. A slow provider
    must not hold up the response."""
    from sqlalchemy import select

    from app.models import OutboxEvent

    user = await _register(client, register_payload)
    await client.post("/auth/forgot-password", json={"email": user["email"]})

    rows = list(
        await session.scalars(
            select(OutboxEvent).where(OutboxEvent.topic == "notification-events")
        )
    )
    assert len(rows) == 1
    assert user["email"] in rows[0].payload


@pytest.mark.parametrize("too_short", ["short", "1234567"])
async def test_a_new_password_must_still_meet_the_length_rule(
    client, register_payload, too_short
):
    """A reset must not be a way around the rule registration enforces."""
    user = await _register(client, register_payload)
    token = await _reset_token(client, user["email"])

    r = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": too_short}
    )
    assert r.status_code == 422, r.text


async def test_cors_headers_are_sent_for_an_allowed_origin(client):
    """CORS_ORIGINS was set by the deploy and documented as required, but no
    middleware read it — so in production the browser rejected every
    cross-origin auth call while the setting sat there looking configured."""
    r = await client.options(
        "/auth/forgot-password",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert r.headers.get("access-control-allow-credentials") == "true"


async def test_an_unlisted_origin_gets_no_cors_grant(client):
    r = await client.options(
        "/auth/forgot-password",
        headers={
            "Origin": "https://not-our-frontend.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None

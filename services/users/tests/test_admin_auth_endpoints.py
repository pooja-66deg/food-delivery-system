"""The admin auth routes, exercised over HTTP rather than through the service layer.

test_admin_password_reset.py already pins ``reset_admin_password``'s conditions by
calling it directly. That is the right place for those rules and the wrong place
to learn what the *endpoint* does, because the parts that were broken here were
never in the service layer: the role check that ``/auth/admin/login`` skipped and
the missing-secret check on ``/auth/internal/bootstrap-admin`` both live in the
router, and a service-level test passes regardless of either.

So these drive the app. Where a test needs configuration that differs from the
defaults, it monkeypatches ``settings`` — the routes read it at call time, which
is what makes that work.
"""

import pytest

from app.config import settings
from app.schemas import UserRegister
from app.service import bootstrap_admin, register_user, reset_admin_password


async def _make_customer(session, email="cara@example.com"):
    return await register_user(session, UserRegister(
        email=email, phone="+919876543210",
        first_name="Cara", last_name="Customer",
        password="supersecret1", role="customer",
    ))


async def _make_ready_admin(session, email="admin@test.com", password="AdminPassword123"):
    """An admin past the forced first-login reset, i.e. one who can actually sign in."""
    await bootstrap_admin(session, email, "TempPassword123")
    await reset_admin_password(session, email, "TempPassword123", password)


# --------------------------------------------------------------------------
# POST /auth/admin/login
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_login_refuses_a_customer_with_correct_credentials(client, session):
    """The bug this route shipped with: a customer signing in as an admin.

    The old handler verified the password, checked the reset flag only when the
    account was an admin, and otherwise fell through to the ordinary login — so
    this request returned 200 and a valid token, which the console stored under
    its admin key and treated as an operator session.
    """
    await _make_customer(session)

    response = await client.post(
        "/auth/admin/login",
        json={"email": "cara@example.com", "password": "supersecret1"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()


@pytest.mark.asyncio
async def test_admin_login_refuses_a_customer_indistinguishably_from_a_bad_password(
    client, session
):
    """A valid non-admin credential must not be told it was valid.

    Answering 403 "not an administrator" here would confirm the password was
    right, which makes this route a password oracle for every non-admin account
    — worse than the blunt error an operator sees after mistyping their address.
    """
    await _make_customer(session)

    correct = await client.post(
        "/auth/admin/login",
        json={"email": "cara@example.com", "password": "supersecret1"},
    )
    wrong = await client.post(
        "/auth/admin/login",
        json={"email": "cara@example.com", "password": "wrongpassword1"},
    )

    assert correct.status_code == wrong.status_code == 401
    assert correct.json() == wrong.json()


@pytest.mark.asyncio
async def test_admin_login_succeeds_for_an_admin_past_the_forced_reset(client, session):
    await _make_ready_admin(session)

    response = await client.post(
        "/auth/admin/login",
        json={"email": "admin@test.com", "password": "AdminPassword123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_login_demands_the_reset_before_issuing_a_token(client, session):
    """A freshly bootstrapped admin gets the 403 the console routes to the reset page."""
    await bootstrap_admin(session, "admin@test.com", "TempPassword123")

    response = await client.post(
        "/auth/admin/login",
        json={"email": "admin@test.com", "password": "TempPassword123"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["password_reset_required"] is True
    assert body["email"] == "admin@test.com"
    assert "access_token" not in body


@pytest.mark.asyncio
async def test_admin_login_refuses_an_unknown_address(client):
    response = await client.post(
        "/auth/admin/login",
        json={"email": "nobody@test.com", "password": "supersecret1"},
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------
# /auth/admin/gate
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_status_reports_no_gate_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_gate_password", None)

    response = await client.get("/auth/admin/gate")

    assert response.status_code == 200
    assert response.json() == {"gate_required": False}


@pytest.mark.asyncio
async def test_gate_status_reports_a_gate_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_gate_password", "s3cret-gate")

    response = await client.get("/auth/admin/gate")

    assert response.status_code == 200
    assert response.json() == {"gate_required": True}


@pytest.mark.asyncio
async def test_gate_accepts_the_configured_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_gate_password", "s3cret-gate")

    response = await client.post("/auth/admin/gate", json={"password": "s3cret-gate"})

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_gate_refuses_a_wrong_password_with_403_not_401(client, monkeypatch):
    """403 is deliberate and the SPA depends on it.

    The API client signs the current user out whenever a non-admin call answers
    401, so refusing a mistyped gate password that way would log a signed-in
    customer out of an unrelated tab. No identity is involved at the gate, so
    "forbidden" is both accurate and free of that side effect.
    """
    monkeypatch.setattr(settings, "admin_gate_password", "s3cret-gate")

    response = await client.post("/auth/admin/gate", json={"password": "wrong"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_gate_is_open_when_unconfigured(client, monkeypatch):
    """No gate configured means nothing to pass, matching what the GET advertises.

    Refusing instead would lock the console out of every deployment that never
    set the variable — which is every local checkout.
    """
    monkeypatch.setattr(settings, "admin_gate_password", None)

    response = await client.post("/auth/admin/gate", json={"password": "anything"})

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_gate_handles_a_non_ascii_password(client, monkeypatch):
    """``compare_digest`` raises TypeError on non-ASCII str, which would be a 500.

    Both sides are encoded before comparing, so an operator whose password has an
    accent in it gets a working gate rather than a server error.
    """
    monkeypatch.setattr(settings, "admin_gate_password", "contraseña-segura")

    accepted = await client.post(
        "/auth/admin/gate", json={"password": "contraseña-segura"}
    )
    refused = await client.post("/auth/admin/gate", json={"password": "contrasena"})

    assert accepted.status_code == 204
    assert refused.status_code == 403


@pytest.mark.asyncio
async def test_bootstrap_refuses_rather_than_errors_on_a_non_ascii_configured_secret(
    client, monkeypatch
):
    """A misconfigured secret must refuse, not 500.

    HTTP header values are ASCII, so a non-ASCII secret can never be *sent* — but
    it can certainly be *configured*, and an operator who pastes one has made the
    route unusable either way. The difference is whether the endpoint answers
    "no" or leaks a stack trace: ``compare_digest`` raises TypeError on non-ASCII
    str, so without encoding both sides this is a 500 on every attempt.
    """
    monkeypatch.setattr(settings, "bootstrap_secret", "clé-de-démarrage")

    response = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "cle-de-demarrage"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_gate_password_is_not_disclosed_by_the_status_route(client, monkeypatch):
    """The probe says whether a gate exists, never what opens it."""
    monkeypatch.setattr(settings, "admin_gate_password", "s3cret-gate")

    body = (await client.get("/auth/admin/gate")).text

    assert "s3cret-gate" not in body


# --------------------------------------------------------------------------
# POST /auth/internal/bootstrap-admin
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_is_disabled_when_no_secret_is_configured(client, monkeypatch):
    """Unset configuration closes the route rather than opening it.

    "internal" was a description of intent, not of routing: the gateway proxies
    /api/auth/ straight here, so this was reachable by anyone and the first
    caller on a fresh deployment became its administrator. Treating an unset
    secret as "no secret required" would reproduce that on exactly the
    deployments nobody has finished configuring.
    """
    monkeypatch.setattr(settings, "bootstrap_secret", None)

    response = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "attacker@evil.com", "password": "TempPassword123"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_refuses_a_missing_header(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    response = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "attacker@evil.com", "password": "TempPassword123"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_refuses_a_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    response = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "attacker@evil.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "guessed"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_answers_identically_whether_disabled_or_wrong(
    client, monkeypatch
):
    """Whether this deployment can still be bootstrapped is not worth leaking."""
    monkeypatch.setattr(settings, "bootstrap_secret", None)
    disabled = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "a@evil.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "guessed"},
    )

    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")
    wrong = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "a@evil.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "guessed"},
    )

    assert disabled.status_code == wrong.status_code == 401
    assert disabled.json() == wrong.json()


@pytest.mark.asyncio
async def test_bootstrap_succeeds_with_the_configured_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    response = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "bootstrap-me"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_bootstrapped_admin_must_reset_before_it_can_sign_in(client, monkeypatch):
    """The two halves of the flow, over HTTP, in the order an operator meets them."""
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    created = await client.post(
        "/auth/internal/bootstrap-admin",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "bootstrap-me"},
    )
    assert created.status_code == 201

    blocked = await client.post(
        "/auth/admin/login",
        json={"email": "admin@test.com", "password": "TempPassword123"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["password_reset_required"] is True

    reset = await client.post(
        "/auth/admin/reset-password",
        json={
            "email": "admin@test.com",
            "old_password": "TempPassword123",
            "new_password": "NewPassword456",
        },
    )
    assert reset.status_code == 200

    signed_in = await client.post(
        "/auth/admin/login",
        json={"email": "admin@test.com", "password": "NewPassword456"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["access_token"]


# --------------------------------------------------------------------------
# POST /auth/admin/reset-password
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_reset_password_endpoint_refuses_a_customer(client, session):
    """The service layer enforces this; here it is confirmed over the wire.

    Before the role check existed, this unauthenticated route would change any
    account's password given its current one.
    """
    await _make_customer(session)

    response = await client.post(
        "/auth/admin/reset-password",
        json={
            "email": "cara@example.com",
            "old_password": "supersecret1",
            "new_password": "NewPassword456",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_reset_password_endpoint_is_rate_limited(client, session):
    """An unauthenticated password-verification route needs a ceiling on guesses."""
    await bootstrap_admin(session, "admin@test.com", "TempPassword123")

    statuses = []
    for _ in range(settings.auth_rate_max + 2):
        response = await client.post(
            "/auth/admin/reset-password",
            json={
                "email": "admin@test.com",
                "old_password": "WrongPassword",
                "new_password": "NewPassword456",
            },
        )
        statuses.append(response.status_code)

    assert 429 in statuses, f"never rate limited: {statuses}"

"""Tests for the advisory email-verification flow."""
import pytest

from src.modules.users import router as users_router

EMAIL = "verifyme@example.com"
PASSWORD = "supersecret1"


async def _register(api_client):
    return await api_client.post("/auth/register", json={
        "email": EMAIL, "phone": "+15559820001", "first_name": "Vee", "last_name": "Ess",
        "password": PASSWORD, "role": "customer"})


async def _signed_in(api_client):
    await _register(api_client)
    tokens = (await api_client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _token_from(mail) -> str:
    """Pull the verification token out of an emailed link.

    Registration returns UserResponse, which carries no debug_token, so tests
    read the token the same way a real user does — out of the message body.
    """
    return mail["message"].split("/verify-email?token=")[1].split()[0]


@pytest.fixture
def sent(monkeypatch):
    """Capture outbound notifications instead of dispatching them."""
    captured = []

    async def _capture(channel, to, message, subject=None):
        captured.append({"channel": channel, "to": to, "message": message, "subject": subject})
        return True

    monkeypatch.setattr(users_router.senders, "dispatch", _capture)
    return captured


@pytest.mark.asyncio
async def test_new_account_starts_unverified(api_client):
    headers = await _signed_in(api_client)
    me = (await api_client.get("/users/me", headers=headers)).json()
    assert me["is_email_verified"] is False


@pytest.mark.asyncio
async def test_request_then_confirm_verifies_the_account(api_client, sent):
    headers = await _signed_in(api_client)

    requested = await api_client.post("/auth/verify-email/request", headers=headers)
    assert requested.status_code == 202
    token = requested.json()["debug_token"]

    assert (await api_client.post(
        "/auth/verify-email/confirm", json={"token": token})).status_code == 204

    me = (await api_client.get("/users/me", headers=headers)).json()
    assert me["is_email_verified"] is True


@pytest.mark.asyncio
async def test_request_emails_a_verification_link(api_client, sent):
    headers = await _signed_in(api_client)
    await api_client.post("/auth/verify-email/request", headers=headers)

    # Two now: one from registration, one from the explicit request.
    assert len(sent) == 2
    mail = sent[-1]
    assert mail["channel"] == "EMAIL"
    assert mail["to"] == EMAIL
    assert "/verify-email?token=" in mail["message"]
    assert mail["subject"] and "Order update" not in mail["subject"]


@pytest.mark.asyncio
async def test_confirm_is_single_use(api_client, sent):
    headers = await _signed_in(api_client)
    token = (await api_client.post(
        "/auth/verify-email/request", headers=headers)).json()["debug_token"]

    await api_client.post("/auth/verify-email/confirm", json={"token": token})
    replay = await api_client.post("/auth/verify-email/confirm", json={"token": token})
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_unknown_token_is_rejected(api_client):
    resp = await api_client.post("/auth/verify-email/confirm", json={"token": "not-a-real-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_confirm_does_not_require_a_signed_in_session(api_client, sent):
    """The link is opened from a mail client that may not be signed in."""
    headers = await _signed_in(api_client)
    token = (await api_client.post(
        "/auth/verify-email/request", headers=headers)).json()["debug_token"]

    resp = await api_client.post("/auth/verify-email/confirm", json={"token": token})
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_request_requires_authentication(api_client):
    assert (await api_client.post("/auth/verify-email/request")).status_code == 401


@pytest.mark.asyncio
async def test_registering_emails_a_verification_link(api_client, sent):
    assert (await _register(api_client)).status_code == 201

    assert len(sent) == 1
    mail = sent[0]
    assert mail["channel"] == "EMAIL"
    assert mail["to"] == EMAIL
    assert "/verify-email?token=" in mail["message"]


@pytest.mark.asyncio
async def test_token_from_the_registration_email_verifies_the_account(api_client, sent):
    await _register(api_client)
    token = _token_from(sent[0])

    assert (await api_client.post(
        "/auth/verify-email/confirm", json={"token": token})).status_code == 204

    tokens = (await api_client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD})).json()
    me = (await api_client.get("/users/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}"})).json()
    assert me["is_email_verified"] is True


@pytest.mark.asyncio
async def test_register_succeeds_when_the_mail_transport_fails(api_client, monkeypatch):
    """The account is committed before the email is attempted, so a provider
    outage must not turn a successful signup into a 500."""
    async def _boom(channel, to, message, subject=None):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(users_router.senders, "dispatch", _boom)

    assert (await _register(api_client)).status_code == 201

    login = await api_client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_a_duplicate_registration_sends_no_email(api_client, sent):
    await _register(api_client)
    sent.clear()

    assert (await _register(api_client)).status_code == 409
    assert sent == []


@pytest.mark.asyncio
async def test_verifying_an_already_verified_account_is_idempotent(api_client, sent):
    headers = await _signed_in(api_client)

    for _ in range(2):
        token = (await api_client.post(
            "/auth/verify-email/request", headers=headers)).json()["debug_token"]
        assert (await api_client.post(
            "/auth/verify-email/confirm", json={"token": token})).status_code == 204

    me = (await api_client.get("/users/me", headers=headers)).json()
    assert me["is_email_verified"] is True

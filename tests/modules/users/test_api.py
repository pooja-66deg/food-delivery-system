"""End-to-end API tests for the users/auth routes."""

import pytest

REGISTER = {
    "email": "api@example.com",
    "phone": "+15554440000",
    "first_name": "Api",
    "last_name": "User",
    "password": "supersecret1",
}


async def _register(api_client, **overrides):
    payload = {**REGISTER, **overrides}
    return await api_client.post("/auth/register", json=payload)


async def _auth_header(api_client):
    await _register(api_client)
    resp = await api_client.post(
        "/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_register_returns_user_without_password(api_client):
    resp = await _register(api_client)

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == REGISTER["email"]
    assert body["role"] == "customer"
    assert "password" not in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(api_client):
    await _register(api_client)
    resp = await _register(api_client)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_token_then_wrong_password_401(api_client):
    await _register(api_client)

    ok = await api_client.post(
        "/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await api_client.post(
        "/auth/login", json={"email": REGISTER["email"], "password": "nope"}
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(api_client):
    resp = await api_client.get("/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(api_client):
    headers = await _auth_header(api_client)

    resp = await api_client.get("/users/me", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["email"] == REGISTER["email"]


@pytest.mark.asyncio
async def test_update_profile(api_client):
    headers = await _auth_header(api_client)

    resp = await api_client.patch("/users/me", json={"first_name": "Renamed"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Renamed"


@pytest.mark.asyncio
async def test_address_create_list_delete(api_client):
    headers = await _auth_header(api_client)
    addr = {"label": "home", "line1": "1 Main St", "city": "Metropolis", "postal_code": "12345"}

    created = await api_client.post("/users/me/addresses", json=addr, headers=headers)
    assert created.status_code == 201
    address_id = created.json()["id"]

    listed = await api_client.get("/users/me/addresses", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await api_client.delete(f"/users/me/addresses/{address_id}", headers=headers)
    assert deleted.status_code == 204

    empty = await api_client.get("/users/me/addresses", headers=headers)
    assert empty.json() == []


@pytest.mark.asyncio
async def test_otp_request_and_verify_flow(api_client):
    await _register(api_client)

    requested = await api_client.post("/auth/otp/request", json={"phone": REGISTER["phone"]})
    assert requested.status_code == 200
    code = requested.json()["debug_otp"]  # exposed only outside production

    verified = await api_client.post(
        "/auth/otp/verify", json={"phone": REGISTER["phone"], "otp": code}
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"]

"""Tests for auth hardening: refresh/revocation, 500-bug fixes, rate limiting."""
import pytest


async def _register(api_client, email="u@x.com", phone="+15559800001", pw="supersecret1"):
    return await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": pw, "role": "customer"})


@pytest.mark.asyncio
async def test_refresh_issues_new_pair(api_client):
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()
    resp = await api_client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]


@pytest.mark.asyncio
async def test_rotated_refresh_token_is_revoked(api_client):
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()
    old_refresh = login["refresh_token"]
    await api_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    # reusing the rotated token must fail
    replay = await api_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(api_client):
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()
    assert (await api_client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})).status_code == 204
    after = await api_client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_the_access_token_too(api_client):
    """Clearing the refresh token is not enough — the bearer token has up to 30
    minutes left on it."""
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert (await api_client.get("/users/me", headers=headers)).status_code == 200

    await api_client.post("/auth/logout", json={"refresh_token": login["refresh_token"]}, headers=headers)

    assert (await api_client.get("/users/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_logout_without_bearer_still_revokes_the_refresh_token(api_client):
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()

    assert (await api_client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})).status_code == 204
    assert (await api_client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_access_token_rejected_at_refresh(api_client):
    await _register(api_client)
    login = (await api_client.post("/auth/login", json={"email": "u@x.com", "password": "supersecret1"})).json()
    resp = await api_client.post("/auth/refresh", json={"refresh_token": login["access_token"]})
    assert resp.status_code == 401  # wrong token type


@pytest.mark.asyncio
async def test_duplicate_registration_returns_409(api_client):
    assert (await _register(api_client)).status_code == 201
    dup = await _register(api_client)  # same email + phone
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_overlong_password_returns_422_not_500(api_client):
    resp = await _register(api_client, pw="a" * 100)  # >72 bytes
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_numeric_sub_returns_401_not_500(api_client):
    from src.core.jwt import create_access_token
    token = create_access_token({"sub": "not-a-number", "role": "customer"})
    resp = await api_client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limited(api_client):
    await _register(api_client)
    codes = []
    for _ in range(12):  # limit is 10 per window
        r = await api_client.post("/auth/login", json={"email": "u@x.com", "password": "wrongpass"})
        codes.append(r.status_code)
    assert 429 in codes

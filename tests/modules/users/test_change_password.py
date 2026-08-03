"""Tests for the authenticated change-password flow and the session eviction
it triggers."""
import pytest

EMAIL = "changer@example.com"
OLD = "supersecret1"
NEW = "brandnewpass9"


async def _register(api_client):
    return await api_client.post("/auth/register", json={
        "email": EMAIL, "phone": "+15559810001", "first_name": "Cee", "last_name": "Pea",
        "password": OLD, "role": "customer"})


async def _login(api_client, password=OLD):
    return await api_client.post("/auth/login", json={"email": EMAIL, "password": password})


def _auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _change(api_client, tokens, current=OLD, new=NEW):
    return await api_client.post(
        "/users/me/change-password",
        json={"current_password": current, "new_password": new},
        headers=_auth(tokens),
    )


@pytest.mark.asyncio
async def test_wrong_current_password_is_rejected(api_client):
    await _register(api_client)
    tokens = (await _login(api_client)).json()

    assert (await _change(api_client, tokens, current="notmypassword")).status_code == 401
    # the original password still works
    assert (await _login(api_client)).status_code == 200


@pytest.mark.asyncio
async def test_change_password_swaps_the_credentials(api_client):
    await _register(api_client)
    tokens = (await _login(api_client)).json()

    assert (await _change(api_client, tokens)).status_code == 200
    assert (await _login(api_client, OLD)).status_code == 401
    assert (await _login(api_client, NEW)).status_code == 200


@pytest.mark.asyncio
async def test_caller_stays_signed_in_with_the_returned_pair(api_client):
    await _register(api_client)
    tokens = (await _login(api_client)).json()

    fresh = (await _change(api_client, tokens)).json()
    me = await api_client.get("/users/me", headers=_auth(fresh))
    assert me.status_code == 200
    assert (await api_client.post(
        "/auth/refresh", json={"refresh_token": fresh["refresh_token"]})).status_code == 200


@pytest.mark.asyncio
async def test_other_devices_are_evicted(api_client):
    await _register(api_client)
    first = (await _login(api_client)).json()
    second = (await _login(api_client)).json()

    assert (await _change(api_client, first)).status_code == 200

    assert (await api_client.get("/users/me", headers=_auth(second))).status_code == 401
    assert (await api_client.post(
        "/auth/refresh", json={"refresh_token": second["refresh_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_the_token_that_made_the_change_is_evicted_too(api_client):
    """Only the pair returned by the call survives; the one used to make it
    belongs to the old generation."""
    await _register(api_client)
    tokens = (await _login(api_client)).json()

    await _change(api_client, tokens)

    assert (await api_client.get("/users/me", headers=_auth(tokens))).status_code == 401


@pytest.mark.asyncio
async def test_change_password_requires_authentication(api_client):
    resp = await api_client.post(
        "/users/me/change-password", json={"current_password": OLD, "new_password": NEW})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_short_new_password_is_rejected(api_client):
    await _register(api_client)
    tokens = (await _login(api_client)).json()

    assert (await _change(api_client, tokens, new="short")).status_code == 422

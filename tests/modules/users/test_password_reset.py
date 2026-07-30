"""Forgot-password / reset-password flow."""
import pytest


async def _register(api_client, email="pw@x.com", phone="+15551119999", pw="supersecret1"):
    return await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "P", "last_name": "W",
        "password": pw, "role": "customer"})


@pytest.mark.asyncio
async def test_full_reset_flow(api_client):
    await _register(api_client)
    # request a reset — dev returns the token for convenience
    forgot = await api_client.post("/auth/forgot-password", json={"email": "pw@x.com"})
    assert forgot.status_code == 200
    token = forgot.json()["debug_token"]

    # old password no longer needed — reset to a new one
    reset = await api_client.post("/auth/reset-password", json={"token": token, "new_password": "brandnew123"})
    assert reset.status_code == 204

    # old password fails, new password works
    assert (await api_client.post("/auth/login", json={"email": "pw@x.com", "password": "supersecret1"})).status_code == 401
    assert (await api_client.post("/auth/login", json={"email": "pw@x.com", "password": "brandnew123"})).status_code == 200


@pytest.mark.asyncio
async def test_reset_token_is_single_use(api_client):
    await _register(api_client)
    token = (await api_client.post("/auth/forgot-password", json={"email": "pw@x.com"})).json()["debug_token"]
    assert (await api_client.post("/auth/reset-password", json={"token": token, "new_password": "brandnew123"})).status_code == 204
    # reusing the same token fails
    again = await api_client.post("/auth/reset-password", json={"token": token, "new_password": "another12345"})
    assert again.status_code == 401


@pytest.mark.asyncio
async def test_forgot_unknown_email_does_not_reveal(api_client):
    resp = await api_client.post("/auth/forgot-password", json={"email": "nobody@x.com"})
    assert resp.status_code == 200
    assert "debug_token" not in resp.json()  # no token issued, no enumeration


@pytest.mark.asyncio
async def test_invalid_token_rejected(api_client):
    resp = await api_client.post("/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever12"})
    assert resp.status_code == 401

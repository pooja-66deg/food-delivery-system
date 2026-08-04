"""HTTP surface for channel preferences and push devices."""
import pytest


async def _login(api_client, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": "supersecret1", "role": "customer"})
    tok = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_preferences_default_to_email_and_push(api_client):
    headers = await _login(api_client, "pref1@x.com", "+15559830001")

    body = (await api_client.get("/notifications/preferences", headers=headers)).json()

    assert body == {"email_enabled": True, "sms_enabled": False, "push_enabled": True}


@pytest.mark.asyncio
async def test_patch_preferences_persists_and_leaves_others_alone(api_client):
    headers = await _login(api_client, "pref2@x.com", "+15559830002")

    patched = await api_client.patch(
        "/notifications/preferences", json={"sms_enabled": True}, headers=headers
    )

    assert patched.status_code == 200
    assert patched.json() == {"email_enabled": True, "sms_enabled": True, "push_enabled": True}
    # Survives a re-read rather than only living in the response.
    reread = (await api_client.get("/notifications/preferences", headers=headers)).json()
    assert reread["sms_enabled"] is True


@pytest.mark.asyncio
async def test_device_registration_lifecycle(api_client):
    headers = await _login(api_client, "dev1@x.com", "+15559830003")

    created = await api_client.post(
        "/notifications/devices", json={"token": "tok-browser01"}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["platform"] == "web"

    listed = (await api_client.get("/notifications/devices", headers=headers)).json()
    assert [d["token"] for d in listed] == ["tok-browser01"]

    removed = await api_client.delete("/notifications/devices/tok-browser01", headers=headers)
    assert removed.status_code == 204
    assert (await api_client.get("/notifications/devices", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_unregistering_an_unknown_token_is_404(api_client):
    headers = await _login(api_client, "dev2@x.com", "+15559830004")

    resp = await api_client.delete("/notifications/devices/tok-neverseen", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_user_cannot_unregister_another_users_device(api_client):
    owner = await _login(api_client, "dev3@x.com", "+15559830005")
    other = await _login(api_client, "dev4@x.com", "+15559830006")
    await api_client.post("/notifications/devices", json={"token": "tok-owned001"}, headers=owner)

    resp = await api_client.delete("/notifications/devices/tok-owned001", headers=other)

    # 404, not 403: the answer must not confirm that the token exists.
    assert resp.status_code == 404
    assert (await api_client.get("/notifications/devices", headers=owner)).json()


@pytest.mark.asyncio
async def test_a_too_short_token_is_rejected(api_client):
    headers = await _login(api_client, "dev5@x.com", "+15559830007")

    resp = await api_client.post("/notifications/devices", json={"token": "abc"}, headers=headers)

    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/notifications/preferences"),
        ("patch", "/notifications/preferences"),
        ("get", "/notifications/devices"),
        ("post", "/notifications/devices"),
        ("get", "/notifications/deliveries"),
    ],
)
async def test_channel_endpoints_require_auth(api_client, method, path):
    call = getattr(api_client, method)
    resp = await (call(path, json={}) if method in ("patch", "post") else call(path))

    assert resp.status_code == 401

"""Driver status, live location (Redis GEO), nearby search, nearest assignment, tracking."""
import pytest

from src.modules.delivery import location


# ── unit: Redis GEO helpers ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_online_toggle_and_location(fake_redis):
    await location.set_online(fake_redis, 7, True)
    assert await location.is_online(fake_redis, 7) is True

    await location.update_location(fake_redis, 7, latitude=38.115, longitude=13.361)
    loc = await location.get_location(fake_redis, 7)
    assert loc["latitude"] == pytest.approx(38.115, abs=1e-3)
    assert loc["longitude"] == pytest.approx(13.361, abs=1e-3)

    await location.set_online(fake_redis, 7, False)
    assert await location.is_online(fake_redis, 7) is False
    assert await location.get_location(fake_redis, 7) is None  # removed from GEO


@pytest.mark.asyncio
async def test_nearby_returns_closest_first(fake_redis):
    await location.update_location(fake_redis, 1, latitude=38.115, longitude=13.361)  # close
    await location.update_location(fake_redis, 2, latitude=37.502, longitude=15.087)  # ~200km
    near = await location.nearby_driver_ids(fake_redis, latitude=38.11, longitude=13.36, radius_km=10)
    assert near == [1]  # only the close driver within 10km


# ── integration: nearest-driver assignment + tracking ────────────────────────
async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_nearest_driver_assigned_and_tracking(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559610001")
    # restaurant with coordinates
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00",
        "latitude": 38.11, "longitude": 13.36}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()

    # two drivers online: near and far
    near = await _login(api_client, "driver", "near@x.com", "+15559610002")
    far = await _login(api_client, "driver", "far@x.com", "+15559610003")
    await api_client.post("/delivery/location", json={"latitude": 38.115, "longitude": 13.361}, headers=near)
    await api_client.post("/delivery/location", json={"latitude": 37.502, "longitude": 15.087}, headers=far)

    # customer places an order
    cust = await _login(api_client, "customer", "c@x.com", "+15559610004")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]

    # owner accepts and readies -> nearest driver ("near") should be assigned
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)

    assert any(a["order_id"] == oid for a in (await api_client.get("/delivery/assignments", headers=near)).json())
    assert (await api_client.get("/delivery/assignments", headers=far)).json() == []

    # customer tracks the order -> sees the assigned driver's live location
    track = await api_client.get(f"/delivery/orders/{oid}/tracking", headers=cust)
    assert track.status_code == 200
    body = track.json()
    assert body["status"] == "ASSIGNED"
    assert body["driver"] is not None


@pytest.mark.asyncio
async def test_driver_status_endpoint(api_client):
    driver = await _login(api_client, "driver", "d@x.com", "+15559610005")
    resp = await api_client.post("/delivery/status", json={"online": True}, headers=driver)
    assert resp.status_code == 200 and resp.json()["online"] is True

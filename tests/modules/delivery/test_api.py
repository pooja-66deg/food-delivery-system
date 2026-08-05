"""Delivery + driver flow, verified end-to-end."""
import pytest

from src.modules.orders.models import OrderStatus
from src.modules.payments.models import PaymentTxStatus


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _place_and_ready(api_client, with_driver=True):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559600001")
    driver = await _login(api_client, "driver", "d@x.com", "+15559600009") if with_driver else None
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559600002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)
    return owner, cust, driver, oid


@pytest.mark.asyncio
async def test_driver_pickup_and_deliver_flow(api_client):
    owner, cust, driver, oid = await _place_and_ready(api_client, with_driver=True)

    # driver has the assignment
    assignments = (await api_client.get("/delivery/assignments", headers=driver)).json()
    assert any(a["order_id"] == oid and a["status"] == "ASSIGNED" for a in assignments)

    notes = (await api_client.get("/notifications", headers=driver)).json()
    assert any(n["type"] == "delivery.assigned" and n["order_id"] == oid for n in notes)

    # pickup advances the order to OUT_FOR_DELIVERY
    pu = await api_client.post(f"/delivery/orders/{oid}/pickup", headers=driver)
    assert pu.status_code == 200 and pu.json()["status"] == "PICKED_UP"
    assert (await api_client.get(f"/orders/{oid}", headers=cust)).json()["status"] == OrderStatus.OUT_FOR_DELIVERY.value

    # deliver advances the order to DELIVERED and settles the (COD) payment
    dv = await api_client.post(f"/delivery/orders/{oid}/deliver", headers=driver)
    assert dv.status_code == 200 and dv.json()["status"] == "DELIVERED"
    assert (await api_client.get(f"/orders/{oid}", headers=cust)).json()["status"] == OrderStatus.DELIVERED.value
    assert (await api_client.get(f"/payments/order/{oid}", headers=cust)).json()["status"] == PaymentTxStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_unassigned_when_no_driver_available(api_client):
    owner, cust, _, oid = await _place_and_ready(api_client, with_driver=False)
    # no driver exists -> a driver registering later has no assignment
    driver = await _login(api_client, "driver", "late@x.com", "+15559600010")
    assert (await api_client.get("/delivery/assignments", headers=driver)).json() == []


@pytest.mark.asyncio
async def test_other_driver_cannot_pickup(api_client):
    owner, cust, driver, oid = await _place_and_ready(api_client, with_driver=True)
    other = await _login(api_client, "driver", "other@x.com", "+15559600011")
    assert (await api_client.post(f"/delivery/orders/{oid}/pickup", headers=other)).status_code == 403


# ── tracking payload: coordinates, ETA, and who may read it ──────────────────
async def _ready_with_coords(api_client, suffix):
    """A READY_FOR_PICKUP order whose restaurant has coordinates and whose
    driver has posted a live position."""
    owner = await _login(api_client, "restaurant", f"{suffix}-o@x.com", f"+1555964{suffix}1")
    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00",
        "latitude": 12.9352, "longitude": 77.6245}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories",
        json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"},
        headers=owner)).json()

    driver = await _login(api_client, "driver", f"{suffix}-d@x.com", f"+1555964{suffix}2")
    await api_client.post("/delivery/location",
        json={"latitude": 12.9716, "longitude": 77.5946}, headers=driver)

    cust = await _login(api_client, "customer", f"{suffix}-c@x.com", f"+1555964{suffix}3")
    await api_client.post("/cart/items",
        json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis",
        "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr["id"], "price_hash": ph}, headers=cust)).json()["id"]

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)
    return owner, cust, driver, oid


@pytest.mark.asyncio
async def test_tracking_includes_coordinates_and_eta(api_client):
    _, cust, _, oid = await _ready_with_coords(api_client, "1")

    body = (await api_client.get(f"/delivery/orders/{oid}/tracking", headers=cust)).json()

    assert body["driver"]["latitude"] == pytest.approx(12.9716, abs=1e-3)
    assert body["restaurant"]["latitude"] == pytest.approx(12.9352, abs=1e-3)
    # The test address is not geocodable and no geocoder is configured, so the
    # destination is unknown and the ETA covers driver -> restaurant only.
    assert body["destination"] is None
    assert body["eta_minutes"] is not None
    assert body["eta_source"] == "estimate"
    assert body["distance_km"] > 0


@pytest.mark.asyncio
async def test_assignments_carry_next_stop_coordinates(api_client):
    _, _, driver, oid = await _ready_with_coords(api_client, "2")

    assignments = (await api_client.get("/delivery/assignments", headers=driver)).json()
    mine = next(a for a in assignments if a["order_id"] == oid)

    assert mine["restaurant"]["latitude"] == pytest.approx(12.9352, abs=1e-3)
    assert mine["destination"] is None  # test address is not geocodable


@pytest.mark.asyncio
async def test_driver_cannot_read_the_tracking_endpoint(api_client):
    """Tracking is customer/owner/admin only; drivers use their assignments."""
    _, _, driver, oid = await _ready_with_coords(api_client, "3")

    resp = await api_client.get(f"/delivery/orders/{oid}/tracking", headers=driver)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_eta_shortens_once_the_restaurant_leg_is_behind(api_client):
    """Picking up drops the restaurant waypoint, so the ETA must not be stale."""
    _, cust, driver, oid = await _ready_with_coords(api_client, "4")

    await api_client.post(f"/delivery/orders/{oid}/accept", headers=driver)
    before = (await api_client.get(f"/delivery/orders/{oid}/tracking", headers=cust)).json()

    await api_client.post(f"/delivery/orders/{oid}/pickup", headers=driver)
    after = (await api_client.get(f"/delivery/orders/{oid}/tracking", headers=cust)).json()

    assert before["status"] == "ACCEPTED"
    assert after["status"] == "PICKED_UP"
    # Before pickup: driver -> restaurant. After: driver -> destination, which is
    # unknown here, so no ETA can be computed at all.
    assert before["eta_minutes"] is not None
    assert after["eta_minutes"] is None

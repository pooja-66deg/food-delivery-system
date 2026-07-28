import pytest

from src.modules.orders.models import OrderStatus


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _seed(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559300001")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559300002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return owner, cust, addr, ph


@pytest.mark.asyncio
async def test_full_order_lifecycle(api_client):
    owner, cust, addr, ph = await _seed(api_client)
    order = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()
    oid = order["id"]

    assert (await api_client.post(f"/orders/{oid}/accept", headers=owner)).json()["status"] == OrderStatus.RESTAURANT_ACCEPTED.value
    for to in ["PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED"]:
        r = await api_client.post(f"/orders/{oid}/status", json={"to": to}, headers=owner)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == to

    # customer sees it in history
    hist = (await api_client.get("/orders", headers=cust)).json()
    assert any(o["id"] == oid for o in hist)


@pytest.mark.asyncio
async def test_customer_cancel_and_ownership(api_client):
    owner, cust, addr, ph = await _seed(api_client)
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    # another customer cannot view it
    other = await _login(api_client, "customer", "c2@x.com", "+15559300003")
    assert (await api_client.get(f"/orders/{oid}", headers=other)).status_code == 403
    # owner cannot skip straight to DELIVERED
    assert (await api_client.post(f"/orders/{oid}/status", json={"to": "DELIVERED"}, headers=owner)).status_code == 409
    # customer cancels (pre-prep) -> full refund
    c = (await api_client.post(f"/orders/{oid}/cancel", headers=cust)).json()
    assert c["status"] == OrderStatus.CANCELLED.value and c["refund_status"] == "FULL"


@pytest.mark.asyncio
async def test_checkout_requires_auth(api_client):
    assert (await api_client.post("/orders/checkout", json={"address_id": 1, "price_hash": "x"})).status_code == 401

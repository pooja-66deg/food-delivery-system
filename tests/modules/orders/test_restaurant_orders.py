"""Restaurant can list its incoming orders and is notified of new ones."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _place(api_client, owner):
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559540002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    return rid, oid, cust


@pytest.mark.asyncio
async def test_restaurant_sees_orders_and_new_order_notification(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559540001")
    rid, oid, _ = await _place(api_client, owner)

    orders = (await api_client.get(f"/orders/restaurant/{rid}", headers=owner)).json()
    assert any(o["id"] == oid for o in orders)

    # owner is notified of the new order
    notes = (await api_client.get("/notifications", headers=owner)).json()
    assert any(n["type"] == "order.new" and n["order_id"] == oid for n in notes)

    # and can accept it
    acc = await api_client.post(f"/orders/{oid}/accept", headers=owner)
    assert acc.status_code == 200 and acc.json()["status"] == "RESTAURANT_ACCEPTED"


@pytest.mark.asyncio
async def test_other_owner_cannot_list_orders(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559540001")
    rid, _, _ = await _place(api_client, owner)
    other = await _login(api_client, "restaurant", "o2@x.com", "+15559540009")
    assert (await api_client.get(f"/orders/restaurant/{rid}", headers=other)).status_code == 403

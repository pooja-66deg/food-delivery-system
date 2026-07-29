"""Notifications generated on order status changes."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_customer_notified_through_lifecycle(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559700001")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559700002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]

    # after checkout there is a PAYMENT_SUCCESS notification
    notes = (await api_client.get("/notifications", headers=cust)).json()
    assert any(n["type"] == "order.PAYMENT_SUCCESS" and n["order_id"] == oid for n in notes)

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    notes = (await api_client.get("/notifications", headers=cust)).json()
    assert any(n["type"] == "order.RESTAURANT_ACCEPTED" for n in notes)


@pytest.mark.asyncio
async def test_notifications_require_auth(api_client):
    assert (await api_client.get("/notifications")).status_code == 401

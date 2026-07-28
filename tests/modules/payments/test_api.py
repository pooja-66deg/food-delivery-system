"""Payments verified end-to-end through the order lifecycle."""
import pytest

from src.modules.payments.models import PaymentTxStatus


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _place_order(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559500001")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559500002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    return owner, cust, oid


@pytest.mark.asyncio
async def test_payment_created_on_checkout(api_client):
    owner, cust, oid = await _place_order(api_client)
    p = (await api_client.get(f"/payments/order/{oid}", headers=cust)).json()
    assert p["provider"] == "COD"
    assert p["status"] == PaymentTxStatus.AUTHORIZED.value
    assert p["amount"] == "20.00"


@pytest.mark.asyncio
async def test_payment_settles_on_delivery(api_client):
    owner, cust, oid = await _place_order(api_client)
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    for to in ["PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED"]:
        await api_client.post(f"/orders/{oid}/status", json={"to": to}, headers=owner)
    p = (await api_client.get(f"/payments/order/{oid}", headers=cust)).json()
    assert p["status"] == PaymentTxStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_payment_refunded_on_customer_cancel(api_client):
    owner, cust, oid = await _place_order(api_client)
    await api_client.post(f"/orders/{oid}/cancel", headers=cust)
    p = (await api_client.get(f"/payments/order/{oid}", headers=cust)).json()
    assert p["status"] == PaymentTxStatus.REFUNDED.value

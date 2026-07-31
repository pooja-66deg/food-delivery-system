"""Driver accepts or rejects an assignment; reject reassigns to another driver."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _ready_order(api_client, owner):
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559620004")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)
    return oid


@pytest.mark.asyncio
async def test_driver_accept_then_pickup(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559620001")
    driver = await _login(api_client, "driver", "d1@x.com", "+15559620002")
    oid = await _ready_order(api_client, owner)

    acc = await api_client.post(f"/delivery/orders/{oid}/accept", headers=driver)
    assert acc.status_code == 200 and acc.json()["status"] == "ACCEPTED"
    pu = await api_client.post(f"/delivery/orders/{oid}/pickup", headers=driver)
    assert pu.status_code == 200 and pu.json()["status"] == "PICKED_UP"


@pytest.mark.asyncio
async def test_driver_reject_reassigns_to_other_driver(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559620001")
    d1 = await _login(api_client, "driver", "d1@x.com", "+15559620002")
    d2 = await _login(api_client, "driver", "d2@x.com", "+15559620003")
    oid = await _ready_order(api_client, owner)

    # whoever holds the assignment rejects it; it should move to the other driver
    holder, other = (d1, d2) if (await api_client.get("/delivery/assignments", headers=d1)).json() else (d2, d1)
    rej = await api_client.post(f"/delivery/orders/{oid}/reject", headers=holder)
    assert rej.status_code == 200
    assert rej.json()["driver_id"] is not None  # reassigned, not left unassigned
    # the other driver now holds it; the rejecter does not
    assert any(a["order_id"] == oid for a in (await api_client.get("/delivery/assignments", headers=other)).json())
    assert not any(a["order_id"] == oid for a in (await api_client.get("/delivery/assignments", headers=holder)).json())

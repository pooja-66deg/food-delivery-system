"""Reviews: customer rates a delivered order; owner gets a review notification."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _delivered_order(api_client, owner, cust):
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    for to in ["PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED"]:
        await api_client.post(f"/orders/{oid}/status", json={"to": to}, headers=owner)
    return rid, oid


@pytest.mark.asyncio
async def test_review_delivered_order_notifies_owner(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559630001")
    cust = await _login(api_client, "customer", "c@x.com", "+15559630002")
    rid, oid = await _delivered_order(api_client, owner, cust)

    r = await api_client.post("/reviews", json={"order_id": oid, "rating": 5, "comment": "Great!"}, headers=cust)
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 5

    # public listing shows it
    listing = (await api_client.get(f"/reviews/restaurant/{rid}")).json()
    assert len(listing) == 1 and listing[0]["comment"] == "Great!"

    # the owner received a review notification
    notes = (await api_client.get("/notifications", headers=owner)).json()
    assert any(n["type"] == "review.created" for n in notes)


@pytest.mark.asyncio
async def test_cannot_review_before_delivered(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559630003")
    cust = await _login(api_client, "customer", "c@x.com", "+15559630004")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]

    # order is only PAYMENT_SUCCESS, not delivered -> 409
    resp = await api_client.post("/reviews", json={"order_id": oid, "rating": 4}, headers=cust)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_double_review_rejected(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559630005")
    cust = await _login(api_client, "customer", "c@x.com", "+15559630006")
    _, oid = await _delivered_order(api_client, owner, cust)
    assert (await api_client.post("/reviews", json={"order_id": oid, "rating": 5}, headers=cust)).status_code == 201
    assert (await api_client.post("/reviews", json={"order_id": oid, "rating": 3}, headers=cust)).status_code == 409

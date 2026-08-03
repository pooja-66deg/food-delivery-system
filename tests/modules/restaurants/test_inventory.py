"""Tests for menu-item stock: derived availability and the checkout gate."""

import pytest


async def _owner_with_item(api_client, stock=None, email="stock@example.com",
                           phone="+15557790001", city="Metropolis"):
    """Create an open restaurant with one item, optionally stock-tracked."""
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "Sto", "last_name": "Ck",
        "password": "supersecret1", "role": "restaurant"})
    owner = {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": email, "password": "supersecret1"})).json()["access_token"]}

    rid = (await api_client.post("/restaurants", headers=owner, json={
        "name": "Stock Cafe", "city": city, "address_line": "1 Main St",
        "phone": "+15550000000"})).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", headers=owner, json={"is_open": True})
    cat = (await api_client.post(f"/restaurants/{rid}/categories", headers=owner,
                                 json={"name": "Mains"})).json()
    payload = {"category_id": cat["id"], "name": "Pizza", "price": "10.00"}
    if stock is not None:
        payload["stock_quantity"] = stock
    item = (await api_client.post(f"/restaurants/{rid}/items", headers=owner,
                                  json=payload)).json()
    return owner, rid, item


async def _customer_with_cart(api_client, item_id, quantity,
                              email="stockcust@example.com", phone="+15557790002"):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "Cus", "last_name": "Tom",
        "password": "supersecret1", "role": "customer"})
    cust = {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": email, "password": "supersecret1"})).json()["access_token"]}
    await api_client.post("/cart/items", headers=cust,
                          json={"menu_item_id": item_id, "quantity": quantity})
    await api_client.post("/users/me/addresses", headers=cust, json={
        "label": "home", "line1": "1 Main St", "city": "Metropolis", "postal_code": "12345"})
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return cust, addr, price_hash


@pytest.mark.asyncio
async def test_untracked_item_is_in_stock(api_client):
    """Items that predate inventory must keep working unchanged."""
    _, _, item = await _owner_with_item(api_client)

    assert item["stock_quantity"] is None
    assert item["in_stock"] is True


@pytest.mark.asyncio
async def test_tracked_item_reports_its_count(api_client):
    _, _, item = await _owner_with_item(api_client, stock=4)

    assert item["stock_quantity"] == 4
    assert item["in_stock"] is True


@pytest.mark.asyncio
async def test_zero_stock_is_out_of_stock_without_touching_the_manual_flag(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=0)

    # The owner's switch is untouched; only the derived field changes.
    assert item["is_available"] is True
    assert item["in_stock"] is False


@pytest.mark.asyncio
async def test_manual_unavailable_beats_positive_stock(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=9)

    updated = (await api_client.patch(f"/restaurants/{rid}/items/{item['id']}",
                                      headers=owner, json={"is_available": False})).json()

    assert updated["stock_quantity"] == 9
    assert updated["in_stock"] is False


@pytest.mark.asyncio
async def test_stock_can_be_updated_and_cleared(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=2)
    url = f"/restaurants/{rid}/items/{item['id']}"

    restocked = (await api_client.patch(url, headers=owner,
                                        json={"stock_quantity": 25})).json()
    assert restocked["stock_quantity"] == 25

    untracked = (await api_client.patch(url, headers=owner,
                                        json={"stock_quantity": None})).json()
    assert untracked["stock_quantity"] is None
    assert untracked["in_stock"] is True


@pytest.mark.asyncio
async def test_negative_stock_is_rejected(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=2)

    resp = await api_client.patch(f"/restaurants/{rid}/items/{item['id']}",
                                  headers=owner, json={"stock_quantity": -1})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_menu_exposes_stock_to_customers(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=3)

    detail = (await api_client.get(f"/restaurants/{rid}")).json()
    listed = detail["menu"][0]["items"][0]

    assert listed["stock_quantity"] == 3
    assert listed["in_stock"] is True


@pytest.mark.asyncio
async def test_checkout_rejects_a_line_above_remaining_stock(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=1)
    cust, addr, price_hash = await _customer_with_cart(api_client, item["id"], 2)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={"address_id": addr, "price_hash": price_hash})

    assert resp.status_code == 422
    assert resp.json()["detail"] == "'Pizza' is no longer available." or \
        "Pizza" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ordering_decrements_tracked_stock(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=5)
    cust, addr, price_hash = await _customer_with_cart(api_client, item["id"], 2)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={"address_id": addr, "price_hash": price_hash})
    assert resp.status_code == 201, resp.text

    detail = (await api_client.get(f"/restaurants/{rid}")).json()
    assert detail["menu"][0]["items"][0]["stock_quantity"] == 3


@pytest.mark.asyncio
async def test_ordering_leaves_untracked_stock_alone(api_client):
    owner, rid, item = await _owner_with_item(api_client)
    cust, addr, price_hash = await _customer_with_cart(api_client, item["id"], 2)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={"address_id": addr, "price_hash": price_hash})
    assert resp.status_code == 201, resp.text

    detail = (await api_client.get(f"/restaurants/{rid}")).json()
    assert detail["menu"][0]["items"][0]["stock_quantity"] is None


@pytest.mark.asyncio
async def test_selling_the_last_portion_makes_it_out_of_stock(api_client):
    owner, rid, item = await _owner_with_item(api_client, stock=2)
    cust, addr, price_hash = await _customer_with_cart(api_client, item["id"], 2)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={"address_id": addr, "price_hash": price_hash})
    assert resp.status_code == 201, resp.text

    listed = (await api_client.get(f"/restaurants/{rid}")).json()["menu"][0]["items"][0]
    assert listed["stock_quantity"] == 0
    assert listed["in_stock"] is False

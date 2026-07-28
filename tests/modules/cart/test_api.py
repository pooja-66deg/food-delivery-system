"""End-to-end API tests for cart & checkout."""

import pytest


async def _register_login(api_client, *, role, email, phone):
    await api_client.post(
        "/auth/register",
        json={"email": email, "phone": phone, "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role},
    )
    resp = await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_restaurant(api_client, owner_headers):
    r = await api_client.post(
        "/restaurants",
        json={"name": "Pizza", "city": "Metropolis", "address_line": "1 St", "phone": "+15550000000", "min_order_amount": "5.00"},
        headers=owner_headers,
    )
    rid = r.json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner_headers)
    cat = await api_client.post(f"/restaurants/{rid}/categories", json={"name": "Mains"}, headers=owner_headers)
    item = await api_client.post(
        f"/restaurants/{rid}/items",
        json={"category_id": cat.json()["id"], "name": "Pizza", "price": "10.00"},
        headers=owner_headers,
    )
    return rid, item.json()["id"]


@pytest.mark.asyncio
async def test_cart_add_get_and_checkout_flow(api_client):
    owner = await _register_login(api_client, role="restaurant", email="owner@example.com", phone="+15559000001")
    _, item_id = await _seed_restaurant(api_client, owner)
    cust = await _register_login(api_client, role="customer", email="cust@example.com", phone="+15559000002")

    # add to cart
    add = await api_client.post("/cart/items", json={"menu_item_id": item_id, "quantity": 2}, headers=cust)
    assert add.status_code == 200
    assert add.json()["subtotal"] == "20.00"

    # a delivery address in the same city
    await api_client.post(
        "/users/me/addresses",
        json={"label": "home", "line1": "1 Main", "city": "Metropolis", "postal_code": "12345"},
        headers=cust,
    )
    addresses = await api_client.get("/users/me/addresses", headers=cust)
    address_id = addresses.json()[0]["id"]

    # read cart to obtain the current price hash
    cart = await api_client.get("/cart", headers=cust)
    price_hash = cart.json()["price_hash"]

    # checkout validation
    checkout = await api_client.post(
        "/cart/checkout", json={"address_id": address_id, "price_hash": price_hash}, headers=cust
    )
    assert checkout.status_code == 200
    body = checkout.json()
    assert body["subtotal"] == "20.00"
    assert body["items"][0]["menu_item_id"] == item_id


@pytest.mark.asyncio
async def test_checkout_below_minimum_returns_422_with_code(api_client):
    owner = await _register_login(api_client, role="restaurant", email="o2@example.com", phone="+15559000003")
    # min order high
    r = await api_client.post(
        "/restaurants",
        json={"name": "Fancy", "city": "Metropolis", "address_line": "1", "phone": "+15550000000", "min_order_amount": "50.00"},
        headers=owner,
    )
    rid = r.json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = await api_client.post(f"/restaurants/{rid}/categories", json={"name": "Mains"}, headers=owner)
    item = await api_client.post(f"/restaurants/{rid}/items", json={"category_id": cat.json()["id"], "name": "Snack", "price": "10.00"}, headers=owner)

    cust = await _register_login(api_client, role="customer", email="c2@example.com", phone="+15559000004")
    await api_client.post("/cart/items", json={"menu_item_id": item.json()["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses", json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    address_id = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]

    resp = await api_client.post("/cart/checkout", json={"address_id": address_id, "price_hash": price_hash}, headers=cust)
    assert resp.status_code == 422
    assert resp.json()["errors"]["code"] == "MIN_ORDER_NOT_MET"


@pytest.mark.asyncio
async def test_cart_requires_auth(api_client):
    resp = await api_client.get("/cart")
    assert resp.status_code == 401

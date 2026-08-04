"""End-to-end API tests for restaurants & menu routes."""

import pytest


async def _token(api_client, *, role, email, phone):
    await api_client.post(
        "/auth/register",
        json={
            "email": email, "phone": phone, "first_name": "T", "last_name": "U",
            "password": "supersecret1", "role": role,
        },
    )
    resp = await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})
    return resp.json()["access_token"]


async def _owner_headers(api_client):
    token = await _token(api_client, role="restaurant", email="owner@example.com", phone="+15551110001")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_owner_creates_restaurant_with_menu_and_public_can_browse(api_client):
    headers = await _owner_headers(api_client)

    # Create restaurant
    r = await api_client.post(
        "/restaurants",
        json={"name": "Pizza Palace", "city": "Metropolis", "address_line": "1 St", "phone": "+15550000000"},
        headers=headers,
    )
    assert r.status_code == 201
    rid = r.json()["id"]

    # Add a category and item
    cat = await api_client.post(f"/restaurants/{rid}/categories", json={"name": "Mains"}, headers=headers)
    assert cat.status_code == 201
    cid = cat.json()["id"]
    item = await api_client.post(
        f"/restaurants/{rid}/items",
        json={"category_id": cid, "name": "Margherita", "price": "9.50"},
        headers=headers,
    )
    assert item.status_code == 201

    # Public browse: list (no auth)
    listing = await api_client.get("/restaurants")
    assert listing.status_code == 200
    assert any(x["name"] == "Pizza Palace" for x in listing.json()["items"])

    # Public detail with menu (no auth)
    detail = await api_client.get(f"/restaurants/{rid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Pizza Palace"
    assert body["menu"][0]["name"] == "Mains"
    assert body["menu"][0]["items"][0]["name"] == "Margherita"


@pytest.mark.asyncio
async def test_list_filters_by_city_and_search(api_client):
    headers = await _owner_headers(api_client)
    await api_client.post("/restaurants", json={"name": "Pizza Palace", "city": "Metropolis", "address_line": "1", "phone": "+15550000000"}, headers=headers)
    await api_client.post("/restaurants", json={"name": "Sushi Spot", "city": "Gotham", "address_line": "2", "phone": "+15550000001"}, headers=headers)

    metro = await api_client.get("/restaurants", params={"city": "Metropolis"})
    assert [x["name"] for x in metro.json()["items"]] == ["Pizza Palace"]

    search = await api_client.get("/restaurants", params={"search": "sushi"})
    assert [x["name"] for x in search.json()["items"]] == ["Sushi Spot"]


@pytest.mark.asyncio
async def test_customer_cannot_create_restaurant(api_client):
    token = await _token(api_client, role="customer", email="cust@example.com", phone="+15551110009")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await api_client.post(
        "/restaurants",
        json={"name": "Nope", "city": "Metropolis", "address_line": "1", "phone": "+15550000000"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_restaurant_requires_auth(api_client):
    resp = await api_client.post(
        "/restaurants",
        json={"name": "Nope", "city": "Metropolis", "address_line": "1", "phone": "+15550000000"},
    )
    assert resp.status_code == 401

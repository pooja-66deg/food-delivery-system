"""HTTP routes for discovery: suggestions and popular cuisines."""

import pytest


async def _owner_headers(api_client):
    await api_client.post(
        "/auth/register",
        json={
            "email": "owner@example.com", "phone": "+15551110001", "first_name": "T",
            "last_name": "U", "password": "supersecret1", "role": "restaurant",
        },
    )
    resp = await api_client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create(api_client, headers, name, city, cuisine=None):
    body = {"name": name, "city": city, "address_line": "1 St", "phone": "+15550000000"}
    if cuisine is not None:
        body["cuisine"] = cuisine
    resp = await api_client.post("/restaurants", json=body, headers=headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
async def seeded(api_client):
    headers = await _owner_headers(api_client)
    await _create(api_client, headers, "Pizza Palace", "Metropolis", "Italian")
    await _create(api_client, headers, "Pasta Place", "Metropolis", "Italian")
    await _create(api_client, headers, "Sushi Spot", "Gotham", "Japanese")
    await _create(api_client, headers, "Curry Corner", "Metropolis")
    return headers


# ---------- route resolution ----------

@pytest.mark.asyncio
async def test_suggest_route_resolves_before_restaurant_id(seeded, api_client):
    """`/restaurants/{restaurant_id}` takes an int.

    FastAPI matches in declaration order and does not fall through on a failed
    type conversion, so if /suggest is declared after it this returns 422.
    """
    resp = await api_client.get("/restaurants/suggest", params={"q": "pi"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_popular_cuisines_route_resolves(seeded, api_client):
    resp = await api_client.get("/restaurants/cuisines/popular")

    assert resp.status_code == 200


# ---------- suggestions ----------

@pytest.mark.asyncio
async def test_suggest_returns_matching_names(seeded, api_client):
    resp = await api_client.get("/restaurants/suggest", params={"q": "pi"})

    assert [s["name"] for s in resp.json()] == ["Pizza Palace"]


@pytest.mark.asyncio
async def test_suggest_returns_empty_below_two_characters(seeded, api_client):
    resp = await api_client.get("/restaurants/suggest", params={"q": "p"})

    assert resp.json() == []


@pytest.mark.asyncio
async def test_suggest_payload_is_lightweight(seeded, api_client):
    resp = await api_client.get("/restaurants/suggest", params={"q": "pizza"})

    assert set(resp.json()[0]) == {"id", "name", "city", "cuisine"}


@pytest.mark.asyncio
async def test_suggest_caps_limit(seeded, api_client):
    resp = await api_client.get("/restaurants/suggest", params={"q": "pi", "limit": 999})

    assert resp.status_code == 422


# ---------- popular cuisines ----------

@pytest.mark.asyncio
async def test_popular_cuisines_counts_and_orders(seeded, api_client):
    resp = await api_client.get("/restaurants/cuisines/popular")

    assert resp.json() == [
        {"cuisine": "Italian", "count": 2},
        {"cuisine": "Japanese", "count": 1},
    ]


# ---------- browse filters over HTTP ----------

@pytest.mark.asyncio
async def test_browse_city_filter_ignores_case(seeded, api_client):
    resp = await api_client.get("/restaurants", params={"city": "metropolis"})

    assert {r["name"] for r in resp.json()["items"]} == {"Pizza Palace", "Pasta Place", "Curry Corner"}


@pytest.mark.asyncio
async def test_browse_search_matches_cuisine(seeded, api_client):
    resp = await api_client.get("/restaurants", params={"search": "japanese"})

    assert {r["name"] for r in resp.json()["items"]} == {"Sushi Spot"}

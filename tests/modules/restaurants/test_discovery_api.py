"""Browse endpoint: filters, sort, paging, and the page envelope over HTTP."""
import pytest


async def _owner_headers(api_client):
    await api_client.post("/auth/register", json={
        "email": "disc-owner@example.com", "phone": "+15551220001", "first_name": "T",
        "last_name": "U", "password": "supersecret1", "role": "restaurant"})
    resp = await api_client.post(
        "/auth/login", json={"email": "disc-owner@example.com", "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _restaurant(api_client, headers, name, city="Metropolis", cuisine=None):
    body = {"name": name, "city": city, "address_line": "1 St", "phone": "+15550000000"}
    if cuisine:
        body["cuisine"] = cuisine
    resp = await api_client.post("/restaurants", json=body, headers=headers)
    assert resp.status_code == 201
    rid = resp.json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=headers)
    return rid


async def _item(api_client, headers, rid, name, price, *, vegetarian=False):
    cat = (await api_client.post(
        f"/restaurants/{rid}/categories", json={"name": f"Cat {name}"}, headers=headers)).json()
    resp = await api_client.post(f"/restaurants/{rid}/items", json={
        "category_id": cat["id"], "name": name, "price": price,
        "is_vegetarian": vegetarian}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_browse_returns_a_page_envelope(api_client):
    headers = await _owner_headers(api_client)
    await _restaurant(api_client, headers, "Only One")

    body = (await api_client.get("/restaurants")).json()

    assert body["total"] == 1
    assert body["offset"] == 0
    assert body["limit"] >= 1
    assert [r["name"] for r in body["items"]] == ["Only One"]


@pytest.mark.asyncio
async def test_dish_search_over_http_reports_the_matching_dish(api_client):
    headers = await _owner_headers(api_client)
    rid = await _restaurant(api_client, headers, "Spice Room", cuisine="Indian")
    await _restaurant(api_client, headers, "Taco Stand", cuisine="Mexican")
    await _item(api_client, headers, rid, "Chicken Biryani", "12.00")

    body = (await api_client.get("/restaurants", params={"search": "biryani"})).json()

    assert [r["name"] for r in body["items"]] == ["Spice Room"]
    assert body["items"][0]["matched_items"] == ["Chicken Biryani"]


@pytest.mark.asyncio
async def test_vegetarian_filter_over_http(api_client):
    headers = await _owner_headers(api_client)
    veg = await _restaurant(api_client, headers, "Green Bowl")
    meat = await _restaurant(api_client, headers, "Grill House")
    await _item(api_client, headers, veg, "Paneer Tikka", "9.00", vegetarian=True)
    await _item(api_client, headers, meat, "Lamb Chops", "18.00")

    body = (await api_client.get("/restaurants", params={"vegetarian_only": "true"})).json()

    assert [r["name"] for r in body["items"]] == ["Green Bowl"]


@pytest.mark.asyncio
async def test_price_band_is_reported_on_each_result(api_client):
    headers = await _owner_headers(api_client)
    cheap = await _restaurant(api_client, headers, "Cheap Bites")
    await _item(api_client, headers, cheap, "Roll", "5.00")

    body = (await api_client.get("/restaurants")).json()

    assert body["items"][0]["price_band"] == 1


@pytest.mark.asyncio
async def test_paging_over_http(api_client):
    headers = await _owner_headers(api_client)
    for i in range(3):
        await _restaurant(api_client, headers, f"R{i}")

    page = (await api_client.get("/restaurants", params={"limit": 2, "offset": 2})).json()

    assert [r["name"] for r in page["items"]] == ["R2"]
    assert page["total"] == 3
    assert page["limit"] == 2
    assert page["offset"] == 2


@pytest.mark.asyncio
async def test_sort_by_price_over_http(api_client):
    headers = await _owner_headers(api_client)
    cheap = await _restaurant(api_client, headers, "Zeta Cheap")
    pricey = await _restaurant(api_client, headers, "Alpha Pricey")
    await _item(api_client, headers, cheap, "Roll", "5.00")
    await _item(api_client, headers, pricey, "Tasting", "60.00")

    body = (await api_client.get("/restaurants", params={"sort": "price_low"})).json()

    # Name order would put Alpha first; the price sort must override it.
    assert [r["name"] for r in body["items"]] == ["Zeta Cheap", "Alpha Pricey"]


@pytest.mark.asyncio
async def test_an_unknown_sort_is_rejected_rather_than_silently_ignored(api_client):
    resp = await api_client.get("/restaurants", params={"sort": "whatever"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_a_sort_name_embedded_in_junk_is_rejected(api_client):
    """The validation pattern is anchored; an unanchored one would accept this
    and then fall back to the default sort without telling the caller."""
    resp = await api_client.get("/restaurants", params={"sort": "xratingx"})

    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 5000},
        {"offset": -1},
        {"min_rating": 0},
        {"min_rating": 6},
        {"price_band": 0},
        {"price_band": 9},
    ],
)
async def test_out_of_range_parameters_are_rejected(api_client, params):
    assert (await api_client.get("/restaurants", params=params)).status_code == 422

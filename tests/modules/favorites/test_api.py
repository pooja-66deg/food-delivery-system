"""Favourite restaurants: save, list, remove, and who may do it."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": "supersecret1", "role": role})
    tok = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _restaurant(api_client, owner, name):
    rid = (await api_client.post("/restaurants", json={
        "name": name, "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000"}, headers=owner)).json()["id"]
    return rid


@pytest.fixture
async def setup(api_client):
    owner = await _login(api_client, "restaurant", "fav-o@x.com", "+15559950001")
    cust = await _login(api_client, "customer", "fav-c@x.com", "+15559950002")
    first = await _restaurant(api_client, owner, "Pizza Palace")
    second = await _restaurant(api_client, owner, "Sushi Spot")
    return {"owner": owner, "cust": cust, "first": first, "second": second}


@pytest.mark.asyncio
async def test_save_and_list_a_favorite(api_client, setup):
    resp = await api_client.post(
        "/favorites", json={"restaurant_id": setup["first"]}, headers=setup["cust"])

    assert resp.status_code == 204
    listed = (await api_client.get("/favorites", headers=setup["cust"])).json()
    assert [r["name"] for r in listed] == ["Pizza Palace"]


@pytest.mark.asyncio
async def test_favorites_come_back_most_recently_saved_first(api_client, setup):
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])
    await api_client.post("/favorites", json={"restaurant_id": setup["second"]},
                          headers=setup["cust"])

    listed = (await api_client.get("/favorites", headers=setup["cust"])).json()

    assert [r["name"] for r in listed] == ["Sushi Spot", "Pizza Palace"]


@pytest.mark.asyncio
async def test_saving_twice_is_not_an_error_and_does_not_duplicate(api_client, setup):
    """A double tap on a heart must not produce two rows."""
    for _ in range(2):
        resp = await api_client.post(
            "/favorites", json={"restaurant_id": setup["first"]}, headers=setup["cust"])
        assert resp.status_code == 204

    listed = (await api_client.get("/favorites", headers=setup["cust"])).json()
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_favorites_carry_the_same_detail_as_a_browse_card(api_client, setup):
    """So the saved list renders with the identical component."""
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])

    row = (await api_client.get("/favorites", headers=setup["cust"])).json()[0]

    assert "rating_average" in row and "review_count" in row
    assert "price_band" in row and row["matched_items"] == []


@pytest.mark.asyncio
async def test_ids_endpoint_returns_just_the_ids(api_client, setup):
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])

    ids = (await api_client.get("/favorites/ids", headers=setup["cust"])).json()

    assert ids == [setup["first"]]


@pytest.mark.asyncio
async def test_remove_a_favorite(api_client, setup):
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])

    resp = await api_client.delete(f"/favorites/{setup['first']}", headers=setup["cust"])

    assert resp.status_code == 204
    assert (await api_client.get("/favorites", headers=setup["cust"])).json() == []


@pytest.mark.asyncio
async def test_removing_something_not_saved_is_404(api_client, setup):
    resp = await api_client.delete(f"/favorites/{setup['first']}", headers=setup["cust"])

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_one_customer_cannot_remove_anothers_favorite(api_client, setup):
    other = await _login(api_client, "customer", "fav-c2@x.com", "+15559950003")
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])

    resp = await api_client.delete(f"/favorites/{setup['first']}", headers=other)

    # 404, not 403 — the answer must not reveal another user's shortlist.
    assert resp.status_code == 404
    assert len((await api_client.get("/favorites", headers=setup["cust"])).json()) == 1


@pytest.mark.asyncio
async def test_favorites_are_per_user(api_client, setup):
    other = await _login(api_client, "customer", "fav-c3@x.com", "+15559950004")
    await api_client.post("/favorites", json={"restaurant_id": setup["first"]},
                          headers=setup["cust"])

    assert (await api_client.get("/favorites", headers=other)).json() == []


@pytest.mark.asyncio
async def test_favouriting_an_unknown_restaurant_is_404(api_client, setup):
    resp = await api_client.post(
        "/favorites", json={"restaurant_id": 9999}, headers=setup["cust"])

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_restaurant_owner_has_no_favorites(api_client, setup):
    """Favourites are a diner's shortlist."""
    resp = await api_client.get("/favorites", headers=setup["owner"])

    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path", [("get", "/favorites"), ("post", "/favorites")])
async def test_favorites_require_auth(api_client, method, path):
    call = getattr(api_client, method)
    resp = await (call(path, json={"restaurant_id": 1}) if method == "post" else call(path))

    assert resp.status_code == 401

"""What a customer browsing the site can see of other customers' reviews."""

import pytest


async def _login(api_client, role, email, phone, first="Alex", last="Rivera"):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": first, "last_name": last,
        "password": "supersecret1", "role": role})
    token = (await api_client.post("/auth/login", json={
        "email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _restaurant(api_client, owner, name="Pizza Palace"):
    rid = (await api_client.post("/restaurants", headers=owner, json={
        "name": name, "city": "Metropolis", "address_line": "1 Main St",
        "phone": "+15550000000", "min_order_amount": "0"})).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", headers=owner, json={"is_open": True})
    cat = (await api_client.post(f"/restaurants/{rid}/categories", headers=owner,
                                 json={"name": "Mains"})).json()
    item = (await api_client.post(f"/restaurants/{rid}/items", headers=owner, json={
        "category_id": cat["id"], "name": "Pizza", "price": "10.00"})).json()
    return rid, item["id"]


async def _delivered_order(api_client, owner, cust, rid, item_id):
    await api_client.post("/cart/items", headers=cust,
                          json={"menu_item_id": item_id, "quantity": 1})
    existing = (await api_client.get("/users/me/addresses", headers=cust)).json()
    if not existing:
        await api_client.post("/users/me/addresses", headers=cust, json={
            "label": "home", "line1": "1 Main St", "city": "Metropolis",
            "postal_code": "12345"})
        existing = (await api_client.get("/users/me/addresses", headers=cust)).json()
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", headers=cust, json={
        "address_id": existing[0]["id"], "price_hash": price_hash})).json()["id"]
    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    for to in ("PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED"):
        await api_client.post(f"/orders/{oid}/status", headers=owner, json={"to": to})
    return oid


async def _review(api_client, owner, cust, rid, item_id, rating, comment=None):
    oid = await _delivered_order(api_client, owner, cust, rid, item_id)
    resp = await api_client.post("/reviews", headers=cust, json={
        "order_id": oid, "rating": rating, "comment": comment})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_review_names_the_reviewer_by_first_name_and_initial(api_client):
    """Enough to read as a real person without publishing a full name."""
    owner = await _login(api_client, "restaurant", "o1@x.com", "+15559640001", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c1@x.com", "+15559640002", "Alex", "Rivera")
    rid, item_id = await _restaurant(api_client, owner)
    await _review(api_client, owner, cust, rid, item_id, 5, "Great!")

    listing = (await api_client.get(f"/reviews/restaurant/{rid}")).json()

    assert listing[0]["reviewer_name"] == "Alex R."


@pytest.mark.asyncio
async def test_review_list_can_be_paged(api_client):
    owner = await _login(api_client, "restaurant", "o2@x.com", "+15559640003", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c2@x.com", "+15559640004")
    rid, item_id = await _restaurant(api_client, owner)
    for rating in (5, 4, 3):
        await _review(api_client, owner, cust, rid, item_id, rating)

    first = (await api_client.get(f"/reviews/restaurant/{rid}?limit=2")).json()
    second = (await api_client.get(f"/reviews/restaurant/{rid}?limit=2&offset=2")).json()

    assert len(first) == 2
    assert len(second) == 1
    assert {r["id"] for r in first}.isdisjoint({r["id"] for r in second})


@pytest.mark.asyncio
async def test_browse_list_carries_the_rating(api_client):
    owner = await _login(api_client, "restaurant", "o3@x.com", "+15559640005", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c3@x.com", "+15559640006")
    rid, item_id = await _restaurant(api_client, owner)
    for rating in (5, 4):
        await _review(api_client, owner, cust, rid, item_id, rating)

    listed = (await api_client.get("/restaurants", headers=cust)).json()["items"]
    mine = next(r for r in listed if r["id"] == rid)

    assert mine["rating_average"] == 4.5
    assert mine["review_count"] == 2


@pytest.mark.asyncio
async def test_unreviewed_restaurant_reports_null_not_zero(api_client):
    owner = await _login(api_client, "restaurant", "o4@x.com", "+15559640007", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c4@x.com", "+15559640008")
    rid, _ = await _restaurant(api_client, owner)

    listed = (await api_client.get("/restaurants", headers=cust)).json()["items"]
    mine = next(r for r in listed if r["id"] == rid)

    assert mine["rating_average"] is None
    assert mine["review_count"] == 0


@pytest.mark.asyncio
async def test_detail_carries_the_star_breakdown(api_client):
    owner = await _login(api_client, "restaurant", "o5@x.com", "+15559640009", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c5@x.com", "+15559640010")
    rid, item_id = await _restaurant(api_client, owner)
    for rating in (5, 5, 3):
        await _review(api_client, owner, cust, rid, item_id, rating)

    detail = (await api_client.get(f"/restaurants/{rid}")).json()

    assert detail["rating_average"] == 4.3
    assert detail["review_count"] == 3
    assert detail["rating_breakdown"] == {"5": 2, "4": 0, "3": 1, "2": 0, "1": 0}


@pytest.mark.asyncio
async def test_detail_of_an_unreviewed_restaurant_is_empty_not_zero(api_client):
    owner = await _login(api_client, "restaurant", "o6@x.com", "+15559640011", "Ola", "Owner")
    rid, _ = await _restaurant(api_client, owner)

    detail = (await api_client.get(f"/restaurants/{rid}")).json()

    assert detail["rating_average"] is None
    assert detail["review_count"] == 0
    assert detail["rating_breakdown"] == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}


@pytest.mark.asyncio
async def test_review_listing_is_public(api_client):
    """Ratings are part of choosing a restaurant, so they must not need a login."""
    owner = await _login(api_client, "restaurant", "o7@x.com", "+15559640012", "Ola", "Owner")
    cust = await _login(api_client, "customer", "c7@x.com", "+15559640013")
    rid, item_id = await _restaurant(api_client, owner)
    await _review(api_client, owner, cust, rid, item_id, 4, "Solid")

    listing = await api_client.get(f"/reviews/restaurant/{rid}")

    assert listing.status_code == 200
    assert listing.json()[0]["comment"] == "Solid"

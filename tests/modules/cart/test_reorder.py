"""Reorder: refilling the cart from a past order when the menu has moved on."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": "supersecret1", "role": role})
    tok = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def placed(api_client):
    """A delivered two-line order, with the cart emptied by checkout."""
    owner = await _login(api_client, "restaurant", "ro-o@x.com", "+15559960001")
    cust = await _login(api_client, "customer", "ro-c@x.com", "+15559960002")

    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(
        f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    pizza = (await api_client.post(f"/restaurants/{rid}/items", json={
        "category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    salad = (await api_client.post(f"/restaurants/{rid}/items", json={
        "category_id": cat["id"], "name": "Salad", "price": "4.00"}, headers=owner)).json()

    await api_client.post(
        "/cart/items", json={"menu_item_id": pizza["id"], "quantity": 2}, headers=cust)
    await api_client.post(
        "/cart/items", json={"menu_item_id": salad["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={
        "address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]

    return {"owner": owner, "cust": cust, "rid": rid, "oid": oid,
            "pizza": pizza["id"], "salad": salad["id"]}


async def _reorder(api_client, headers, order_id):
    return await api_client.post("/cart/reorder", json={"order_id": order_id}, headers=headers)


@pytest.mark.asyncio
async def test_reorder_refills_the_cart_with_the_same_lines(api_client, placed):
    resp = await _reorder(api_client, placed["cust"], placed["oid"])

    assert resp.status_code == 200
    body = resp.json()
    lines = {i["menu_item_id"]: i["quantity"] for i in body["cart"]["items"]}
    assert lines == {placed["pizza"]: 2, placed["salad"]: 1}
    assert body["skipped"] == []


@pytest.mark.asyncio
async def test_reorder_replaces_whatever_was_in_the_cart(api_client, placed):
    """"Order this again" means this order, not this plus yesterday's leftovers."""
    await api_client.post(
        "/cart/items", json={"menu_item_id": placed["salad"], "quantity": 9},
        headers=placed["cust"])

    body = (await _reorder(api_client, placed["cust"], placed["oid"])).json()

    lines = {i["menu_item_id"]: i["quantity"] for i in body["cart"]["items"]}
    assert lines == {placed["pizza"]: 2, placed["salad"]: 1}


@pytest.mark.asyncio
async def test_a_delisted_item_is_skipped_and_reported(api_client, placed):
    """One missing side dish must not fail the whole reorder."""
    await api_client.patch(
        f"/restaurants/{placed['rid']}/items/{placed['salad']}",
        json={"is_available": False}, headers=placed["owner"])

    body = (await _reorder(api_client, placed["cust"], placed["oid"])).json()

    assert [i["menu_item_id"] for i in body["cart"]["items"]] == [placed["pizza"]]
    assert body["skipped"] == ["Salad — no longer on the menu"]


@pytest.mark.asyncio
async def test_a_sold_out_item_is_skipped_with_its_own_reason(api_client, placed):
    """"Sold out" and "delisted" are different things to a customer."""
    await api_client.patch(
        f"/restaurants/{placed['rid']}/items/{placed['pizza']}",
        json={"stock_quantity": 1}, headers=placed["owner"])  # order wanted 2

    body = (await _reorder(api_client, placed["cust"], placed["oid"])).json()

    assert body["skipped"] == ["Pizza — sold out"]
    assert [i["menu_item_id"] for i in body["cart"]["items"]] == [placed["salad"]]


@pytest.mark.asyncio
async def test_a_price_change_is_not_a_skip(api_client, placed):
    """The new price is simply what it costs now; checkout makes them confirm."""
    await api_client.patch(
        f"/restaurants/{placed['rid']}/items/{placed['pizza']}",
        json={"price": "14.00"}, headers=placed["owner"])

    body = (await _reorder(api_client, placed["cust"], placed["oid"])).json()

    assert body["skipped"] == []
    pizza_line = next(i for i in body["cart"]["items"] if i["menu_item_id"] == placed["pizza"])
    assert pizza_line["unit_price"] == "14.00"


@pytest.mark.asyncio
async def test_a_reordered_cart_can_be_checked_out(api_client, placed):
    """The end-to-end point of the feature."""
    await _reorder(api_client, placed["cust"], placed["oid"])

    cart = (await api_client.get("/cart", headers=placed["cust"])).json()
    addr = (await api_client.get("/users/me/addresses", headers=placed["cust"])).json()[0]["id"]
    resp = await api_client.post("/orders/checkout", json={
        "address_id": addr, "price_hash": cart["price_hash"]}, headers=placed["cust"])

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_another_customer_cannot_reorder_someone_elses_order(api_client, placed):
    other = await _login(api_client, "customer", "ro-c2@x.com", "+15559960003")

    resp = await _reorder(api_client, other, placed["oid"])

    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_the_restaurant_owner_cannot_reorder(api_client, placed):
    """An owner can see the order but has no cart to put it in."""
    resp = await _reorder(api_client, placed["owner"], placed["oid"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reordering_an_unknown_order_is_404(api_client, placed):
    assert (await _reorder(api_client, placed["cust"], 9999)).status_code == 404


@pytest.mark.asyncio
async def test_reorder_requires_auth(api_client):
    assert (await api_client.post("/cart/reorder", json={"order_id": 1})).status_code == 401

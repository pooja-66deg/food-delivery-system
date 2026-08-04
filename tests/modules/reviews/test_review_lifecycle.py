"""Editing, deleting, and replying to a review."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "User",
        "password": "supersecret1", "role": role})
    tok = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _delivered_order(api_client, owner, cust):
    """Walk an order all the way to DELIVERED so it can be reviewed."""
    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(
        f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items", json={
        "category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()

    await api_client.post(
        "/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={
        "address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    for to in ("PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED"):
        resp = await api_client.post(f"/orders/{oid}/status", json={"to": to}, headers=owner)
        assert resp.status_code == 200, resp.text
    return rid, oid


@pytest.fixture
async def reviewed(api_client):
    owner = await _login(api_client, "restaurant", "rl-o@x.com", "+15559900001")
    cust = await _login(api_client, "customer", "rl-c@x.com", "+15559900002")
    rid, oid = await _delivered_order(api_client, owner, cust)
    created = await api_client.post(
        "/reviews", json={"order_id": oid, "rating": 3, "comment": "Fine."}, headers=cust)
    assert created.status_code == 201, created.text
    return {"owner": owner, "cust": cust, "rid": rid, "review": created.json()}


# ---------- create ----------

@pytest.mark.asyncio
async def test_a_new_review_is_not_marked_as_edited(reviewed):
    """updated_at must stay null, or every review reads as tampered with."""
    assert reviewed["review"]["updated_at"] is None
    assert reviewed["review"]["owner_reply"] is None


@pytest.mark.asyncio
async def test_create_returns_the_public_reviewer_name(reviewed):
    assert reviewed["review"]["reviewer_name"] == "T U."


# ---------- edit ----------

@pytest.mark.asyncio
async def test_the_author_can_revise_their_review(api_client, reviewed):
    rid = reviewed["review"]["id"]

    resp = await api_client.patch(
        f"/reviews/{rid}", json={"rating": 5, "comment": "Better than I said."},
        headers=reviewed["cust"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["rating"] == 5
    assert body["comment"] == "Better than I said."
    # Stamped now, so the UI can mark it edited.
    assert body["updated_at"] is not None


@pytest.mark.asyncio
async def test_an_omitted_comment_is_left_alone(api_client, reviewed):
    rid = reviewed["review"]["id"]

    body = (await api_client.patch(
        f"/reviews/{rid}", json={"rating": 4}, headers=reviewed["cust"])).json()

    assert body["rating"] == 4
    assert body["comment"] == "Fine."


@pytest.mark.asyncio
async def test_an_explicit_null_comment_clears_it(api_client, reviewed):
    """Distinct from omitting the field — a bare None cannot say which is meant."""
    rid = reviewed["review"]["id"]

    body = (await api_client.patch(
        f"/reviews/{rid}", json={"comment": None}, headers=reviewed["cust"])).json()

    assert body["comment"] is None
    assert body["rating"] == 3  # untouched


@pytest.mark.asyncio
async def test_another_customer_cannot_edit_someone_elses_review(api_client, reviewed):
    other = await _login(api_client, "customer", "rl-c2@x.com", "+15559900003")

    resp = await api_client.patch(
        f"/reviews/{reviewed['review']['id']}", json={"rating": 1}, headers=other)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_the_restaurant_owner_cannot_rewrite_a_review(api_client, reviewed):
    """An owner may answer criticism, never edit it."""
    resp = await api_client.patch(
        f"/reviews/{reviewed['review']['id']}", json={"rating": 5},
        headers=reviewed["owner"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_an_out_of_range_rating_is_rejected(api_client, reviewed):
    resp = await api_client.patch(
        f"/reviews/{reviewed['review']['id']}", json={"rating": 9},
        headers=reviewed["cust"])

    assert resp.status_code == 422


# ---------- delete ----------

@pytest.mark.asyncio
async def test_the_author_can_withdraw_their_review(api_client, reviewed):
    rid, restaurant_id = reviewed["review"]["id"], reviewed["rid"]

    resp = await api_client.delete(f"/reviews/{rid}", headers=reviewed["cust"])

    assert resp.status_code == 204
    listed = (await api_client.get(f"/reviews/restaurant/{restaurant_id}")).json()
    assert listed == []


@pytest.mark.asyncio
async def test_deleting_a_review_removes_it_from_the_rating(api_client, reviewed):
    restaurant_id = reviewed["rid"]
    await api_client.delete(f"/reviews/{reviewed['review']['id']}", headers=reviewed["cust"])

    detail = (await api_client.get(f"/restaurants/{restaurant_id}")).json()

    assert detail["rating_average"] is None
    assert detail["review_count"] == 0


@pytest.mark.asyncio
async def test_an_owner_cannot_delete_criticism_of_their_own_restaurant(api_client, reviewed):
    resp = await api_client.delete(
        f"/reviews/{reviewed['review']['id']}", headers=reviewed["owner"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_can_moderate_any_review(api_client, reviewed, app_session):
    from sqlalchemy import select
    from src.modules.users.models import User

    admin_headers = await _login(api_client, "customer", "rl-admin@x.com", "+15559900004")
    admin = await app_session.scalar(select(User).where(User.email == "rl-admin@x.com"))
    admin.role = "admin"
    await app_session.commit()

    resp = await api_client.delete(
        f"/reviews/{reviewed['review']['id']}", headers=admin_headers)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_deleting_an_unknown_review_is_404(api_client, reviewed):
    assert (await api_client.delete("/reviews/9999", headers=reviewed["cust"])).status_code == 404


# ---------- owner reply ----------

@pytest.mark.asyncio
async def test_the_owner_can_reply_and_the_reply_is_public(api_client, reviewed):
    rid, restaurant_id = reviewed["review"]["id"], reviewed["rid"]

    resp = await api_client.post(
        f"/reviews/{rid}/reply", json={"reply": "Sorry — we have fixed the oven."},
        headers=reviewed["owner"])

    assert resp.status_code == 200
    assert resp.json()["owner_reply"] == "Sorry — we have fixed the oven."
    assert resp.json()["owner_replied_at"] is not None
    listed = (await api_client.get(f"/reviews/restaurant/{restaurant_id}")).json()
    assert listed[0]["owner_reply"] == "Sorry — we have fixed the oven."


@pytest.mark.asyncio
async def test_replying_again_replaces_the_answer_rather_than_threading(api_client, reviewed):
    rid = reviewed["review"]["id"]
    await api_client.post(f"/reviews/{rid}/reply", json={"reply": "First take"},
                          headers=reviewed["owner"])

    body = (await api_client.post(f"/reviews/{rid}/reply", json={"reply": "Better wording"},
                                  headers=reviewed["owner"])).json()

    assert body["owner_reply"] == "Better wording"


@pytest.mark.asyncio
async def test_a_reply_notifies_the_customer(api_client, reviewed):
    await api_client.post(
        f"/reviews/{reviewed['review']['id']}/reply", json={"reply": "Thanks!"},
        headers=reviewed["owner"])

    feed = (await api_client.get("/notifications", headers=reviewed["cust"])).json()

    assert any(n["type"] == "review.replied" for n in feed)


@pytest.mark.asyncio
async def test_an_unrelated_owner_cannot_reply(api_client, reviewed):
    intruder = await _login(api_client, "restaurant", "rl-o2@x.com", "+15559900005")

    resp = await api_client.post(
        f"/reviews/{reviewed['review']['id']}/reply", json={"reply": "Mine now"},
        headers=intruder)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_a_customer_cannot_post_an_owner_reply(api_client, reviewed):
    resp = await api_client.post(
        f"/reviews/{reviewed['review']['id']}/reply", json={"reply": "I am the owner"},
        headers=reviewed["cust"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_an_empty_reply_is_rejected(api_client, reviewed):
    resp = await api_client.post(
        f"/reviews/{reviewed['review']['id']}/reply", json={"reply": ""},
        headers=reviewed["owner"])

    assert resp.status_code == 422

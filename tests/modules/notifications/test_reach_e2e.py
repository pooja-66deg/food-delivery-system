"""End-to-end: a real order actually reaches the customer off-app.

This is the test that catches a lifecycle transition whose post-commit delivery
call was never wired up — the unit tests would all still pass in that case.
"""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": "supersecret1", "role": role})
    tok = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _place_order(api_client):
    owner = await _login(api_client, "restaurant", "reach-o@x.com", "+15559840001")
    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(
        f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items", json={
        "category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()

    cust = await _login(api_client, "customer", "reach-c@x.com", "+15559840002")
    await api_client.post(
        "/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout", json={
        "address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    return owner, cust, oid


async def _deliveries(api_client, headers) -> list[dict]:
    return (await api_client.get("/notifications/deliveries", headers=headers)).json()


@pytest.mark.asyncio
async def test_checkout_emails_the_confirmation(api_client):
    _, cust, oid = await _place_order(api_client)

    rows = await _deliveries(api_client, cust)

    emails = [r for r in rows if r["channel"] == "EMAIL"]
    assert emails, "COD checkout should email the confirmation"
    assert emails[0]["type"] == "order.PAYMENT_SUCCESS"
    assert emails[0]["order_id"] == oid
    assert emails[0]["delivered"] is True


@pytest.mark.asyncio
async def test_kitchen_steps_reach_a_registered_device_but_send_no_email(api_client):
    owner, cust, oid = await _place_order(api_client)
    await api_client.post(
        "/notifications/devices", json={"token": "tok-browser01"}, headers=cust)

    await api_client.post(f"/orders/{oid}/accept", headers=owner)

    rows = await _deliveries(api_client, cust)
    accepted = [r for r in rows if r["type"] == "order.RESTAURANT_ACCEPTED"]
    assert [r["channel"] for r in accepted] == ["PUSH"]


@pytest.mark.asyncio
async def test_out_for_delivery_texts_a_customer_who_opted_in(api_client):
    owner, cust, oid = await _place_order(api_client)
    await api_client.patch(
        "/notifications/preferences", json={"sms_enabled": True}, headers=cust)
    driver = await _login(api_client, "driver", "reach-d@x.com", "+15559840003")

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)
    pickup = await api_client.post(f"/delivery/orders/{oid}/pickup", headers=driver)
    assert pickup.status_code == 200, pickup.text

    rows = await _deliveries(api_client, cust)
    texted = [r for r in rows if r["type"] == "order.OUT_FOR_DELIVERY" and r["channel"] == "SMS"]
    assert texted, "an opted-in customer should be texted when the driver sets off"


@pytest.mark.asyncio
async def test_cancelling_reaches_the_customer_by_email(api_client):
    _, cust, oid = await _place_order(api_client)

    await api_client.post(f"/orders/{oid}/cancel", headers=cust)

    rows = await _deliveries(api_client, cust)
    assert [r for r in rows if r["type"] == "order.CANCELLED" and r["channel"] == "EMAIL"]


@pytest.mark.asyncio
async def test_the_in_app_feed_is_not_duplicated_by_outbound_copies(api_client):
    owner, cust, oid = await _place_order(api_client)
    await api_client.post(
        "/notifications/devices", json={"token": "tok-browser01"}, headers=cust)
    await api_client.post(f"/orders/{oid}/accept", headers=owner)

    feed = (await api_client.get("/notifications", headers=cust)).json()

    assert all(n["channel"] == "LOG" for n in feed)
    accepted = [n for n in feed if n["type"] == "order.RESTAURANT_ACCEPTED"]
    assert len(accepted) == 1

from decimal import Decimal

import pytest

from src.modules.orders.models import OrderStatus, PaymentStatus


async def _seed_ready_cart(api_client):
    # owner + restaurant + item
    await api_client.post("/auth/register", json={"email": "o@x.com", "phone": "+15559100001",
        "first_name": "O", "last_name": "W", "password": "supersecret1", "role": "restaurant"})
    owner = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "o@x.com", "password": "supersecret1"})).json()["access_token"]}
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    # customer + cart + address
    await api_client.post("/auth/register", json={"email": "c@x.com", "phone": "+15559100002",
        "first_name": "C", "last_name": "U", "password": "supersecret1", "role": "customer"})
    cust = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "c@x.com", "password": "supersecret1"})).json()["access_token"]}
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return cust, addr, price_hash


@pytest.mark.asyncio
async def test_create_order_from_checkout_persists_everything(api_client, fake_redis, db_session):
    # Exercises the /orders/checkout route added in Task 7; asserts the end
    # state the creation service must produce.
    cust, addr, price_hash = await _seed_ready_cart(api_client)
    resp = await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": price_hash}, headers=cust)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == OrderStatus.PAYMENT_SUCCESS.value
    assert body["payment_status"] == PaymentStatus.SUCCESS.value
    assert body["total"] == "20.00"
    assert len(body["items"]) == 1 and body["items"][0]["quantity"] == 2
    # three status events: CREATED, PAYMENT_PENDING, PAYMENT_SUCCESS
    assert [e["to_status"] for e in body["events"]] == [
        OrderStatus.CREATED.value, OrderStatus.PAYMENT_PENDING.value, OrderStatus.PAYMENT_SUCCESS.value]
    # cart cleared
    assert (await api_client.get("/cart", headers=cust)).json()["items"] == []


@pytest.mark.asyncio
async def test_double_submit_lock(fake_redis, db_session):
    from src.modules.orders import service
    await fake_redis.set("order_lock:1", "1")  # simulate in-flight checkout
    from src.modules.orders.state_machine import OrderError
    from src.modules.cart.schemas import CheckoutRequest

    class _U:  # minimal stand-in for User
        id = 1
    with pytest.raises(OrderError) as exc:
        await service.create_order_from_checkout(
            fake_redis, db_session, _U(), CheckoutRequest(address_id=1, price_hash="x"))
    assert exc.value.details["code"] == "CHECKOUT_IN_PROGRESS"

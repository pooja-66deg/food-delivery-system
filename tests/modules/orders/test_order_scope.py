"""The orders list splits into active and past work."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from src.modules.orders.models import (
    Actor, Order, OrderStatus, PaymentStatus,
)
from src.modules.orders.state_machine import apply_transition
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import Address, User

PATH = [
    OrderStatus.PAYMENT_PENDING, OrderStatus.PAYMENT_SUCCESS,
    OrderStatus.RESTAURANT_ACCEPTED, OrderStatus.PREPARING,
    OrderStatus.READY_FOR_PICKUP, OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]


async def _order_at(session, customer_id: int, status: OrderStatus) -> Order:
    order = Order(customer_id=customer_id, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value,
                  payment_status=PaymentStatus.PENDING.value,
                  subtotal=Decimal("10"), total=Decimal("10"))
    session.add(order)
    await session.flush()
    if status == OrderStatus.CANCELLED:
        # Cancellation is reachable straight from CREATED; no walk needed.
        apply_transition(session, order, status, Actor.SYSTEM)
    else:
        for step in PATH:
            if OrderStatus(order.status) == status:
                break
            apply_transition(session, order, step, Actor.SYSTEM)
    await session.commit()
    return order


async def _signed_in(api_client):
    await api_client.post("/auth/register", json={
        "email": "scope@x.com", "phone": "+15559500001", "first_name": "S", "last_name": "C",
        "password": "supersecret1", "role": "customer"})
    return {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": "scope@x.com", "password": "supersecret1"})).json()["access_token"]}


@pytest.fixture
async def orders(api_client, app_session):
    """One order in each interesting state, owned by a signed-in customer."""
    headers = await _signed_in(api_client)
    customer = await app_session.scalar(select(User).where(User.email == "scope@x.com"))
    app_session.add(User(id=99, email="scopeowner@x.com", phone="+15559500099",
                         first_name="O", last_name="W", hashed_password="h", role="restaurant"))
    app_session.add(Restaurant(id=1, owner_id=99, name="R", city="C",
                               address_line="1", phone="+1"))
    app_session.add(Address(id=1, user_id=customer.id, label="h", line1="1",
                            city="C", postal_code="1"))
    await app_session.commit()

    made = {}
    for status in (OrderStatus.PREPARING, OrderStatus.OUT_FOR_DELIVERY,
                   OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        made[status] = await _order_at(app_session, customer.id, status)
    return headers, made


async def _ids(api_client, headers, scope=None):
    url = "/orders" if scope is None else f"/orders?scope={scope}"
    resp = await api_client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return {o["id"] for o in resp.json()}


@pytest.mark.asyncio
async def test_active_scope_excludes_finished_orders(api_client, orders):
    headers, made = orders

    ids = await _ids(api_client, headers, "active")

    assert made[OrderStatus.PREPARING].id in ids
    assert made[OrderStatus.OUT_FOR_DELIVERY].id in ids
    assert made[OrderStatus.DELIVERED].id not in ids
    assert made[OrderStatus.CANCELLED].id not in ids


@pytest.mark.asyncio
async def test_past_scope_is_the_complement(api_client, orders):
    headers, made = orders

    ids = await _ids(api_client, headers, "past")

    assert made[OrderStatus.DELIVERED].id in ids
    assert made[OrderStatus.CANCELLED].id in ids
    assert made[OrderStatus.PREPARING].id not in ids


@pytest.mark.asyncio
async def test_default_returns_everything(api_client, orders):
    headers, made = orders

    ids = await _ids(api_client, headers)

    assert ids == {o.id for o in made.values()}


@pytest.mark.asyncio
async def test_an_unknown_scope_is_rejected(api_client, orders):
    headers, _ = orders

    resp = await api_client.get("/orders?scope=sideways", headers=headers)

    assert resp.status_code == 422

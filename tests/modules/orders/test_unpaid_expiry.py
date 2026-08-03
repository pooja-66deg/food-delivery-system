"""An abandoned card checkout must not hold its stock reservation forever."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.config import settings
from src.modules.orders import service
from src.modules.orders.models import (
    Actor, Order, OrderItem, OrderStatus, PaymentStatus,
)
from src.modules.orders.state_machine import apply_transition
from src.modules.restaurants.models import MenuCategory, MenuItem, Restaurant
from src.modules.users.models import User


async def _order(session, method="CARD", paid=False, stock=3, order_id=None):
    if await session.get(User, 1) is None:
        session.add(User(id=1, email="c@x.com", phone="+1", first_name="c", last_name="u",
                         hashed_password="h", role="customer"))
        session.add(User(id=2, email="o@x.com", phone="+2", first_name="o", last_name="w",
                         hashed_password="h", role="restaurant"))
        session.add(Restaurant(id=1, owner_id=2, name="R", city="C", address_line="1", phone="+1"))
        session.add(MenuCategory(id=1, restaurant_id=1, name="M"))
        session.add(MenuItem(id=1, restaurant_id=1, category_id=1, name="Pizza",
                             price=Decimal("10"), stock_quantity=stock))

    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value, payment_method=method,
                  payment_status=PaymentStatus.PENDING.value,
                  subtotal=Decimal("20"), total=Decimal("20"))
    order.items.append(OrderItem(menu_item_id=1, name="Pizza", unit_price=Decimal("10"),
                                 quantity=2, line_total=Decimal("20")))
    session.add(order)
    await session.flush()
    apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
    if paid:
        apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM)
        order.payment_status = PaymentStatus.SUCCESS.value
    await session.commit()
    return order


def _past_the_window() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.payment_window_seconds + 60)


@pytest.mark.asyncio
async def test_expired_unpaid_order_is_cancelled(db_session):
    order = await _order(db_session)

    expired = await service.expire_unpaid_orders(db_session, now=_past_the_window())

    assert expired == 1
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED.value
    assert order.cancelled_by == Actor.SYSTEM.value


@pytest.mark.asyncio
async def test_expiry_gives_the_stock_back(db_session):
    await _order(db_session, stock=3)

    await service.expire_unpaid_orders(db_session, now=_past_the_window())

    item = await db_session.get(MenuItem, 1)
    await db_session.refresh(item)
    assert item.stock_quantity == 5


@pytest.mark.asyncio
async def test_a_fresh_unpaid_order_is_left_alone(db_session):
    order = await _order(db_session)

    expired = await service.expire_unpaid_orders(db_session, now=datetime.now(timezone.utc))

    assert expired == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_PENDING.value


@pytest.mark.asyncio
async def test_a_paid_order_is_never_swept(db_session):
    order = await _order(db_session, method="COD", paid=True)

    expired = await service.expire_unpaid_orders(db_session, now=_past_the_window())

    assert expired == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_SUCCESS.value


@pytest.mark.asyncio
async def test_expiry_records_why(db_session):
    order = await _order(db_session)

    await service.expire_unpaid_orders(db_session, now=_past_the_window())

    await db_session.refresh(order, ["events"])
    cancelled = [e for e in order.events if e.to_status == OrderStatus.CANCELLED.value]
    assert cancelled and cancelled[-1].reason


@pytest.mark.asyncio
async def test_expiry_route_reports_the_count(api_client, app_session):
    await _order(app_session)
    await api_client.post("/auth/register", json={
        "email": "adm@x.com", "phone": "+15559400001", "first_name": "A", "last_name": "D",
        "password": "supersecret1", "role": "customer"})
    admin = await app_session.get(User, 3)
    admin.role = "admin"
    await app_session.commit()
    headers = {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": "adm@x.com", "password": "supersecret1"})).json()["access_token"]}

    # Nothing is old enough yet, but the route must exist and answer.
    resp = await api_client.post("/orders/internal/expire-unpaid", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"expired": 0}

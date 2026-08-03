"""Cancelling an order must put its stock back.

Without this every cancellation leaks stock and the owner's count stops being
worth reading.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.modules.orders import service
from src.modules.orders.models import Actor, Order, OrderItem, OrderStatus
from src.modules.orders.state_machine import apply_transition
from src.modules.restaurants.models import MenuCategory, MenuItem, Restaurant
from src.modules.users.models import User


async def _order_with_stock(session, status: OrderStatus, stock=5, quantity=2, tracked=True):
    """An order for 2 of an item that has `stock` left (already decremented)."""
    session.add(User(id=1, email="c@x.com", phone="+1", first_name="c", last_name="u",
                     hashed_password="h", role="customer"))
    session.add(User(id=2, email="o@x.com", phone="+2", first_name="o", last_name="w",
                     hashed_password="h", role="restaurant"))
    session.add(Restaurant(id=1, owner_id=2, name="R", city="C", address_line="1", phone="+1"))
    session.add(MenuCategory(id=1, restaurant_id=1, name="M"))
    session.add(MenuItem(id=1, restaurant_id=1, category_id=1, name="Pizza",
                         price=Decimal("10"),
                         stock_quantity=stock if tracked else None))

    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value,
                  subtotal=Decimal("20"), total=Decimal("20"))
    order.items.append(OrderItem(menu_item_id=1, name="Pizza", unit_price=Decimal("10"),
                                 quantity=quantity, line_total=Decimal("20")))
    session.add(order)
    await session.flush()

    for step in [OrderStatus.PAYMENT_PENDING, OrderStatus.PAYMENT_SUCCESS,
                 OrderStatus.RESTAURANT_ACCEPTED, OrderStatus.PREPARING]:
        if OrderStatus(order.status) == status:
            break
        apply_transition(session, order, step, Actor.SYSTEM)
    await session.commit()
    return order


async def _stock(session) -> int | None:
    item = await session.get(MenuItem, 1)
    await session.refresh(item)
    return item.stock_quantity


@pytest.mark.asyncio
async def test_customer_cancel_restores_stock(db_session):
    order = await _order_with_stock(db_session, OrderStatus.PAYMENT_SUCCESS, stock=3)

    await service.cancel_by_customer(db_session, await db_session.get(User, 1), order.id)

    assert await _stock(db_session) == 5


@pytest.mark.asyncio
async def test_restaurant_reject_restores_stock(db_session):
    order = await _order_with_stock(db_session, OrderStatus.PAYMENT_SUCCESS, stock=3)

    await service.reject_by_restaurant(
        db_session, await db_session.get(User, 2), order.id, reason="out of dough")

    assert await _stock(db_session) == 5


@pytest.mark.asyncio
async def test_restaurant_cancel_via_status_restores_stock(db_session):
    order = await _order_with_stock(db_session, OrderStatus.PREPARING, stock=3)

    await service.advance_status(
        db_session, await db_session.get(User, 2), order.id, OrderStatus.CANCELLED)

    assert await _stock(db_session) == 5


@pytest.mark.asyncio
async def test_acceptance_expiry_restores_stock(db_session):
    order = await _order_with_stock(db_session, OrderStatus.PAYMENT_SUCCESS, stock=3)

    expired = await service.expire_pending_acceptances(
        db_session, datetime.now(timezone.utc) + timedelta(hours=1))

    assert expired == 1
    assert await _stock(db_session) == 5


@pytest.mark.asyncio
async def test_untracked_item_is_left_alone_on_cancel(db_session):
    order = await _order_with_stock(db_session, OrderStatus.PAYMENT_SUCCESS, tracked=False)

    await service.cancel_by_customer(db_session, await db_session.get(User, 1), order.id)

    assert await _stock(db_session) is None


@pytest.mark.asyncio
async def test_cancel_survives_a_deleted_menu_item(db_session):
    """OrderItem.menu_item_id carries no foreign key, so the row can outlive the
    menu item it points at."""
    order = await _order_with_stock(db_session, OrderStatus.PAYMENT_SUCCESS, stock=3)
    await db_session.delete(await db_session.get(MenuItem, 1))
    await db_session.commit()

    result = await service.cancel_by_customer(
        db_session, await db_session.get(User, 1), order.id)

    assert result.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_delivered_order_does_not_restore_stock(db_session):
    """Only cancellation puts stock back — a completed sale must not."""
    order = await _order_with_stock(db_session, OrderStatus.PREPARING, stock=3)
    owner = await db_session.get(User, 2)

    await service.advance_status(db_session, owner, order.id, OrderStatus.READY_FOR_PICKUP)

    assert await _stock(db_session) == 3

from decimal import Decimal

import pytest

from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.orders import service
from src.modules.orders.models import Order, OrderStatus
from src.modules.users.models import User


async def _make_order(session, customer_id=1, restaurant_id=1):
    order = Order(customer_id=customer_id, restaurant_id=restaurant_id, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("5"), total=Decimal("5"))
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_list_orders_newest_first(db_session):
    await _make_order(db_session)
    await _make_order(db_session)
    orders = await service.list_orders(db_session, customer_id=1)
    assert len(orders) == 2 and orders[0].id > orders[1].id


@pytest.mark.asyncio
async def test_get_order_forbidden_for_other_customer(db_session):
    order = await _make_order(db_session, customer_id=1)
    other = User(id=99, email="x@y.com", phone="+1", first_name="a", last_name="b",
                 hashed_password="h", role="customer")
    db_session.add(other)
    await db_session.commit()
    with pytest.raises(ForbiddenException):
        await service.get_order_for_user(db_session, other, order.id)


@pytest.mark.asyncio
async def test_get_missing_order_404(db_session):
    user = User(id=1, email="a@b.com", phone="+2", first_name="a", last_name="b",
                hashed_password="h", role="customer")
    db_session.add(user)
    await db_session.commit()
    with pytest.raises(NotFoundException):
        await service.get_order_for_user(db_session, user, 4242)

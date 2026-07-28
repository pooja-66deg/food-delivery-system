from decimal import Decimal

import pytest

from src.modules.orders import service
from src.modules.orders.models import Actor, Order, OrderStatus, RefundStatus
from src.modules.orders.state_machine import OrderError, apply_transition
from src.modules.users.models import User
from src.modules.restaurants.models import Restaurant


async def _order_in(session, status: OrderStatus, customer_id=1, owner_id=2, restaurant_id=1):
    session.add(User(id=customer_id, email=f"c{customer_id}@x.com", phone=f"+{customer_id}",
                     first_name="c", last_name="u", hashed_password="h", role="customer"))
    session.add(User(id=owner_id, email=f"o{owner_id}@x.com", phone=f"+{owner_id}0",
                     first_name="o", last_name="w", hashed_password="h", role="restaurant"))
    session.add(Restaurant(id=restaurant_id, owner_id=owner_id, name="R", city="C",
                           address_line="1", phone="+1"))
    order = Order(customer_id=customer_id, restaurant_id=restaurant_id, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("20"), total=Decimal("20"))
    session.add(order)
    await session.flush()
    # walk to the requested status through SYSTEM transitions
    path = [OrderStatus.PAYMENT_PENDING, OrderStatus.PAYMENT_SUCCESS, OrderStatus.RESTAURANT_ACCEPTED,
            OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP, OrderStatus.OUT_FOR_DELIVERY]
    for step in path:
        if OrderStatus(order.status) == status:
            break
        apply_transition(session, order, step, Actor.SYSTEM)
    await session.commit()
    return order


@pytest.mark.asyncio
async def test_customer_cancel_preprep_full_refund(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    user = await db_session.get(User, 1)
    result = await service.cancel_by_customer(db_session, user, order.id)
    assert result.status == OrderStatus.CANCELLED
    assert result.refund_status == RefundStatus.FULL
    assert result.refund_amount == Decimal("20")


@pytest.mark.asyncio
async def test_customer_cancel_after_prep_rejected(db_session):
    order = await _order_in(db_session, OrderStatus.PREPARING)
    user = await db_session.get(User, 1)
    with pytest.raises(OrderError) as exc:
        await service.cancel_by_customer(db_session, user, order.id)
    assert exc.value.details["code"] == "CANCEL_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_restaurant_accept(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    owner = await db_session.get(User, 2)
    result = await service.accept_by_restaurant(db_session, owner, order.id)
    assert result.status == OrderStatus.RESTAURANT_ACCEPTED


@pytest.mark.asyncio
async def test_restaurant_reject_full_refund(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    owner = await db_session.get(User, 2)
    result = await service.reject_by_restaurant(db_session, owner, order.id, reason="86 the kitchen")
    assert result.status == OrderStatus.REJECTED
    assert result.refund_status == RefundStatus.FULL

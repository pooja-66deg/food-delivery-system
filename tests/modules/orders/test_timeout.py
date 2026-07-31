from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.modules.orders import service
from src.modules.orders.models import Actor, Order, OrderStatus, RefundStatus
from src.modules.orders.state_machine import apply_transition


async def _payment_success_order(session, updated_delta_seconds: int):
    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("20"), total=Decimal("20"))
    session.add(order)
    await session.flush()
    apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
    apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM)
    order.updated_at = datetime.now(timezone.utc) - timedelta(seconds=updated_delta_seconds)
    await session.commit()
    return order


@pytest.mark.asyncio
async def test_expire_past_window(db_session):
    order = await _payment_success_order(db_session, updated_delta_seconds=1000)
    count = await service.expire_pending_acceptances(db_session, now=datetime.now(timezone.utc))
    assert count == 1
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    assert order.refund_status == RefundStatus.FULL


@pytest.mark.asyncio
async def test_within_window_untouched(db_session):
    order = await _payment_success_order(db_session, updated_delta_seconds=10)
    count = await service.expire_pending_acceptances(db_session, now=datetime.now(timezone.utc))
    assert count == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_SUCCESS

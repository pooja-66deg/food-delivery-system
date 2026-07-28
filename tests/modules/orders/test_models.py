"""Model-layer tests for the orders domain."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.modules.orders.models import (
    Order, OrderItem, OrderStatusEvent,
    OrderStatus, PaymentMethod, PaymentStatus, RefundStatus, Actor,
)


@pytest.mark.asyncio
async def test_order_persists_with_items_and_event(db_session):
    order = Order(
        customer_id=1, restaurant_id=1, address_id=1,
        status=OrderStatus.CREATED, payment_method=PaymentMethod.COD,
        payment_status=PaymentStatus.PENDING, subtotal=Decimal("20.00"),
        delivery_fee=Decimal("0"), total=Decimal("20.00"),
        refund_status=RefundStatus.NONE, refund_amount=Decimal("0"),
    )
    order.items.append(
        OrderItem(menu_item_id=5, name="Pizza", unit_price=Decimal("10.00"),
                  quantity=2, line_total=Decimal("20.00"))
    )
    order.events.append(
        OrderStatusEvent(from_status=None, to_status=OrderStatus.CREATED, actor=Actor.SYSTEM)
    )
    db_session.add(order)
    await db_session.commit()
    assert order.id is not None

    # Reload fresh (eager-loading the relationships) to prove it round-trips.
    loaded = (
        await db_session.scalars(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.items), selectinload(Order.events))
        )
    ).one()

    assert loaded.status == OrderStatus.CREATED          # str-enum compares to stored value
    assert loaded.items[0].line_total == Decimal("20.00")
    assert loaded.events[0].to_status == OrderStatus.CREATED

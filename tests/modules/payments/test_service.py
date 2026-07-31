from decimal import Decimal

import pytest

from src.modules.orders.models import Order, OrderStatus
from src.modules.payments import service
from src.modules.payments.models import PaymentTxStatus
from src.modules.payments.providers import CardProvider, CODProvider, provider_for


async def _order(session, total="20.00", method="COD"):
    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.PAYMENT_SUCCESS.value, payment_method=method,
                  subtotal=Decimal(total), total=Decimal(total))
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


def test_provider_selection():
    assert isinstance(provider_for("COD"), CODProvider)
    assert isinstance(provider_for("CARD"), CardProvider)


@pytest.mark.asyncio
async def test_create_payment_is_idempotent(db_session):
    order = await _order(db_session)
    p1 = await service.create_payment_for_order(db_session, order)
    p2 = await service.create_payment_for_order(db_session, order)
    assert p1.id == p2.id
    assert p1.status == PaymentTxStatus.AUTHORIZED
    assert p1.provider == "COD"
    assert p1.amount == Decimal("20.00")


@pytest.mark.asyncio
async def test_settle_marks_succeeded(db_session):
    order = await _order(db_session)
    await service.create_payment_for_order(db_session, order)
    settled = await service.settle_payment(db_session, order)
    assert settled.status == PaymentTxStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_refund_marks_refunded(db_session):
    order = await _order(db_session)
    await service.create_payment_for_order(db_session, order)
    refunded = await service.refund_payment(db_session, order)
    assert refunded.status == PaymentTxStatus.REFUNDED


@pytest.mark.asyncio
async def test_settle_and_refund_noop_without_payment(db_session):
    order = await _order(db_session)
    assert await service.settle_payment(db_session, order) is None
    assert await service.refund_payment(db_session, order) is None


@pytest.mark.asyncio
async def test_card_provider_authorizes_with_reference(db_session):
    order = await _order(db_session, method="CARD")
    payment = await service.create_payment_for_order(db_session, order)
    assert payment.provider == "CARD"
    assert payment.provider_ref == "pi_order-%d" % order.id

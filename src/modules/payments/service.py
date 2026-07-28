"""Payment lifecycle service.

Settle/refund are no-ops when an order has no payment row, so order flows built
directly in tests (bypassing checkout) don't require a payment.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.payments.models import Payment, PaymentTxStatus
from src.modules.payments.providers import PaymentProvider, provider_for


async def get_payment(session: AsyncSession, order_id: int) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.order_id == order_id))


async def create_payment_for_order(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment:
    """Idempotent: returns the existing payment if one already exists for the order."""
    existing = await get_payment(session, order.id)
    if existing is not None:
        return existing

    provider = provider or provider_for(order.payment_method)
    idem = f"order-{order.id}"
    result = await provider.authorize(order.total, idempotency_key=idem)
    payment = Payment(
        order_id=order.id,
        provider=provider.name,
        amount=order.total,
        status=PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value,
        provider_ref=result.reference,
        idempotency_key=idem,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def settle_payment(session: AsyncSession, order) -> Payment | None:
    """Mark the payment collected/captured (called when an order is delivered)."""
    payment = await get_payment(session, order.id)
    if payment is None:
        return None
    payment.status = PaymentTxStatus.SUCCEEDED.value
    await session.commit()
    await session.refresh(payment)
    return payment


async def refund_payment(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment | None:
    """Execute a refund via the provider and mark the payment REFUNDED."""
    payment = await get_payment(session, order.id)
    if payment is None:
        return None
    provider = provider or provider_for(payment.provider)
    await provider.refund(payment.provider_ref, order.total)
    payment.status = PaymentTxStatus.REFUNDED.value
    await session.commit()
    await session.refresh(payment)
    return payment

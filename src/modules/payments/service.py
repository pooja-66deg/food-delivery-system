"""Payment lifecycle service.

Settle/refund are no-ops when an order has no payment row, so order flows built
directly in tests (bypassing checkout) don't require a payment.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.orders.models import Order
from src.modules.payments.models import Payment, PaymentTxStatus
from src.modules.payments.providers import PaymentProvider, provider_for


async def get_payment(session: AsyncSession, order_id: int) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.order_id == order_id))


async def create_payment_for_order(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment:
    """Idempotent: returns the existing payment if one already exists for the order.

    When the provider needs the customer to confirm (a card PaymentIntent), the
    returned object carries the ``client_secret`` as a transient attribute — read
    it with ``client_secret_of``. It is never written to the database.
    """
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
    payment.client_secret = result.client_secret
    return payment


def client_secret_of(payment: Payment | None) -> str | None:
    """The confirmation secret attached by ``create_payment_for_order``, if any.

    Absent for a payment loaded from the database — the secret only exists for
    the response that created it.
    """
    return getattr(payment, "client_secret", None)


async def capture_payment(session: AsyncSession, order) -> Payment | None:
    """Capture an authorized payment (COD: cash collected; card: funds captured).
    Moves AUTHORIZED → SUCCEEDED. No-op if there's no payment."""
    payment = await get_payment(session, order.id)
    if payment is None:
        return None
    payment.status = PaymentTxStatus.SUCCEEDED.value
    await session.commit()
    await session.refresh(payment)
    return payment


# Settling on delivery is a capture; keep the name the order flow calls.
settle_payment = capture_payment


async def retry_payment(session: AsyncSession, order, provider: PaymentProvider | None = None) -> Payment | None:
    """Re-authorize a FAILED payment. Returns the payment unchanged if it isn't
    in a failed state, or None if there's no payment for the order."""
    payment = await get_payment(session, order.id)
    if payment is None:
        return None
    if payment.status != PaymentTxStatus.FAILED.value:
        return payment
    provider = provider or provider_for(payment.provider)
    result = await provider.authorize(order.total, idempotency_key=f"order-{order.id}-retry")
    payment.status = PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value
    payment.provider_ref = result.reference
    await session.commit()
    await session.refresh(payment)
    return payment


async def resume_card_payment(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment | None:
    """Hand back a confirmation secret for an order still awaiting card payment.

    The secret from checkout is never stored, so a customer who closed the tab
    has no way back to it. This mints a fresh PaymentIntent for the same order
    and points the payment row at it; the abandoned one expires on its own.

    Returns the payment unchanged when there is nothing to pay — a settled
    order, or one that was never on card.
    """
    payment = await get_payment(session, order.id)
    if payment is None:
        return None
    if payment.provider != "CARD" or order.status != "PAYMENT_PENDING":
        return payment

    provider = provider or provider_for("CARD")
    result = await provider.authorize(order.total, idempotency_key=f"order-{order.id}-resume")
    payment.status = (
        PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value
    )
    payment.provider_ref = result.reference
    await session.commit()
    await session.refresh(payment)
    payment.client_secret = result.client_secret
    return payment


async def list_for_customer(session: AsyncSession, customer_id: int, limit: int = 50, offset: int = 0) -> list[Payment]:
    stmt = (
        select(Payment)
        .join(Order, Payment.order_id == Order.id)
        .where(Order.customer_id == customer_id)
        .order_by(Payment.id.desc())
        .limit(limit).offset(offset)
    )
    return list(await session.scalars(stmt))


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

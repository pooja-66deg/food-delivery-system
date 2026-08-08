"""Payment lifecycle service.

Settle/refund are no-ops when an order has no payment row, so order flows built
directly in tests (bypassing checkout) don't require a payment.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app import outbox
from app.models import OrderSnapshot, Payment, PaymentTxStatus
from app.providers import PaymentProvider, provider_for


async def get_payment(session: AsyncSession, order_id: int) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.order_id == order_id))


async def create_payment_for_order(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment:
    """Idempotent: returns the existing payment if one already exists for the order.

    When the provider needs the customer to pay on a hosted page, the returned
    object carries the ``checkout_url`` as a transient attribute — read it with
    ``checkout_url_of``. It is never written to the database.
    """
    existing = await get_payment(session, order.order_id)
    if existing is not None:
        return existing

    provider = provider or provider_for(order.payment_method)
    idem = f"order-{order.order_id}"
    result = await provider.authorize(order.total, idempotency_key=idem, order_id=order.order_id)
    payment = Payment(
        order_id=order.order_id,
        provider=provider.name,
        amount=order.total,
        status=PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value,
        provider_ref=result.reference,
        idempotency_key=idem,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    payment.checkout_url = result.checkout_url
    return payment


def checkout_url_of(payment: Payment | None) -> str | None:
    """The hosted checkout URL attached by ``create_payment_for_order``, if any.

    Absent for a payment loaded from the database — the URL only exists for the
    response that created it.
    """
    return getattr(payment, "checkout_url", None)


async def capture_payment(session: AsyncSession, order) -> Payment | None:
    """Capture an authorized payment (COD: cash collected; card: funds captured).
    Moves AUTHORIZED → SUCCEEDED. No-op if there's no payment."""
    payment = await get_payment(session, order.order_id)
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
    payment = await get_payment(session, order.order_id)
    if payment is None:
        return None
    if payment.status != PaymentTxStatus.FAILED.value:
        return payment
    provider = provider or provider_for(payment.provider)
    result = await provider.authorize(
        order.total, idempotency_key=f"order-{order.order_id}-retry", order_id=order.order_id
    )
    payment.status = PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value
    payment.provider_ref = result.reference
    await session.commit()
    await session.refresh(payment)
    return payment


async def resume_card_payment(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment | None:
    """Hand back a checkout URL for an order still awaiting card payment.

    The URL from checkout is never stored, so a customer who closed the tab has
    no way back to it. This opens a fresh Checkout Session for the same order
    and points the payment row at it; the abandoned one expires on its own.

    Returns the payment unchanged when there is nothing to pay — a settled
    order, or one that was never on card.
    """
    payment = await get_payment(session, order.order_id)
    if payment is None:
        return None
    if payment.provider != "CARD" or order.status != "PAYMENT_PENDING":
        return payment

    provider = provider or provider_for("CARD")
    result = await provider.authorize(
        order.total, idempotency_key=f"order-{order.order_id}-resume", order_id=order.order_id
    )
    payment.status = (
        PaymentTxStatus.AUTHORIZED.value if result.ok else PaymentTxStatus.FAILED.value
    )
    payment.provider_ref = result.reference
    await session.commit()
    await session.refresh(payment)
    payment.checkout_url = result.checkout_url
    return payment


async def confirm_card_payment(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment | None:
    """Settle a card order by asking the provider whether it was actually paid.

    The webhook is still the authority, but it is not always reachable — a local
    setup has no public URL for Stripe to call, and in production an event can
    be delayed. This runs when the customer lands back on the order from the
    hosted page: same outcome, driven by the return leg instead.

    Trusting the redirect itself would let anyone mark an order paid by visiting
    a URL, so the payment state is read back from the provider and nothing else
    is taken on faith. Idempotent, and a no-op for anything not awaiting a card.
    """
    payment = await get_payment(session, order.order_id)
    if payment is None:
        return None
    if payment.provider != "CARD" or order.status != "PAYMENT_PENDING":
        return payment

    provider = provider or provider_for("CARD")
    result = await provider.verify(payment.provider_ref)
    if not result.ok:
        return payment

    # Same swap the webhook makes: a refund cannot be issued against a session.
    if result.reference:
        payment.provider_ref = result.reference
    payment.status = PaymentTxStatus.SUCCEEDED.value
    await session.commit()
    await session.refresh(payment)

    # Was a direct call into the orders module. Now an event: money has moved
    # and that fact is durable here, so the confirmation must not be able to
    # fail because the orders service is slow. It advances the order when it
    # reads this.
    outbox.record_event(
        session, "payment-events", str(order.order_id),
        {
            "order_id": order.order_id,
            "payment_status": "SUCCEEDED",
            "provider": payment.provider,
            "amount": str(payment.amount),
        },
    )
    await session.commit()
    return payment


async def list_for_customer(session: AsyncSession, customer_id: int, limit: int = 50, offset: int = 0) -> list[Payment]:
    stmt = (
        select(Payment)
        # Joined against the local snapshot, not another service's orders
        # table. "My payments" stays a single-database read.
        .join(OrderSnapshot, Payment.order_id == OrderSnapshot.order_id)
        .where(OrderSnapshot.customer_id == customer_id)
        .order_by(Payment.id.desc())
        .limit(limit).offset(offset)
    )
    return list(await session.scalars(stmt))


async def refund_payment(
    session: AsyncSession, order, provider: PaymentProvider | None = None
) -> Payment | None:
    """Execute a refund via the provider and mark the payment REFUNDED."""
    payment = await get_payment(session, order.order_id)
    if payment is None:
        return None
    provider = provider or provider_for(payment.provider)
    await provider.refund(payment.provider_ref, order.total)
    payment.status = PaymentTxStatus.REFUNDED.value
    await session.commit()
    await session.refresh(payment)
    return payment

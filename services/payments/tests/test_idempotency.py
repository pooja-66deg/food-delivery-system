"""What happens when the same command arrives twice.

Not a hypothetical. ``shared/messaging.py`` states the contract in its own first
lines — "at-least-once, biased towards repeating rather than dropping" — and the
ways it repeats are all ordinary: a handler that raises leaves the message
unacknowledged, a consumer group rebalance replays from the last committed
offset, a Pub/Sub ack that misses its deadline redelivers. Pub/Sub additionally
guarantees no ordering, so a delayed ``settle`` can arrive *after* the ``refund``
that superseded it.

Every test here failed before the guards in ``app/service.py`` existed, and each
failure moved real money or misreported it. The service-level suite passed
throughout, because none of it ever delivered a command twice.
"""

from decimal import Decimal

import pytest

from app import service as payment_service
from app.models import OrderSnapshot, Payment, PaymentTxStatus
from app.providers import ProviderResult


class CountingProvider:
    """A provider that records what it was actually asked to do.

    The assertions are on the call count rather than the resulting status,
    because the status is the same either way — a payment refunded twice looks
    exactly like a payment refunded once. Only the provider knows the difference,
    which is the whole reason the bug was invisible.
    """

    name = "COD"

    def __init__(self):
        self.authorize_calls = 0
        self.refund_calls = 0

    async def authorize(self, amount, *, idempotency_key=None, order_id=None):
        self.authorize_calls += 1
        return ProviderResult(ok=True, status="authorized", reference=f"ref-{order_id}")

    async def refund(self, reference, amount):
        self.refund_calls += 1
        return ProviderResult(ok=True, status="refunded", reference=reference)


@pytest.fixture
def provider():
    return CountingProvider()


async def _snapshot(session, order_id=1, total="25.00", status="DELIVERED"):
    snap = OrderSnapshot(
        order_id=order_id, customer_id=7, status=status,
        total=Decimal(total), payment_method="COD",
    )
    session.add(snap)
    await session.commit()
    return snap


async def _authorized_payment(session, order_id=1, total="25.00"):
    payment = Payment(
        order_id=order_id, provider="COD", amount=Decimal(total),
        status=PaymentTxStatus.AUTHORIZED.value, provider_ref=f"ref-{order_id}",
        idempotency_key=f"order-{order_id}",
    )
    session.add(payment)
    await session.commit()
    return payment


# --------------------------------------------------------------------------
# refund
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_redelivered_refund_does_not_refund_twice(session, provider):
    """The one that actually sent money back twice.

    ``refund_payment`` called ``provider.refund()`` unconditionally, so every
    redelivery of the same command was another real refund. Nothing downstream
    could tell: the payment reads REFUNDED after one call and after five.
    """
    snap = await _snapshot(session)
    await _authorized_payment(session)

    await payment_service.refund_payment(session, snap, provider=provider)
    await payment_service.refund_payment(session, snap, provider=provider)
    await payment_service.refund_payment(session, snap, provider=provider)

    assert provider.refund_calls == 1


@pytest.mark.asyncio
async def test_refund_still_reports_the_payment_as_refunded_on_replay(session, provider):
    """A no-op must still answer with the payment, not None.

    The consumer treats None as "no payment for this order" and moves on; if a
    replayed refund returned that, a genuine missing-payment bug would be
    indistinguishable from an ordinary duplicate.
    """
    snap = await _snapshot(session)
    await _authorized_payment(session)

    await payment_service.refund_payment(session, snap, provider=provider)
    replayed = await payment_service.refund_payment(session, snap, provider=provider)

    assert replayed is not None
    assert replayed.status == PaymentTxStatus.REFUNDED.value


@pytest.mark.asyncio
async def test_refund_refuses_a_payment_that_never_took_money(session, provider):
    """FAILED never charged anyone, so there is nothing to send back.

    Refunding against a provider reference for a charge that never succeeded is
    at best a provider error and at worst a credit nobody can reclaim.
    """
    snap = await _snapshot(session)
    payment = await _authorized_payment(session)
    payment.status = PaymentTxStatus.FAILED.value
    await session.commit()

    await payment_service.refund_payment(session, snap, provider=provider)

    assert provider.refund_calls == 0


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_settle_arriving_after_a_refund_does_not_mark_it_collected(
    session, provider
):
    """The quiet one: money returned, record says collected.

    ``capture_payment`` assigned SUCCEEDED with no state check, so a settle
    command overtaking a refund moved REFUNDED -> SUCCEEDED. Nothing about the
    resulting row looks wrong, so no reconciliation would ever find it. Pub/Sub
    offers no ordering guarantee, which makes this an expected delivery rather
    than a fault.
    """
    snap = await _snapshot(session)
    await _authorized_payment(session)

    await payment_service.refund_payment(session, snap, provider=provider)
    await payment_service.capture_payment(session, snap)

    payment = await payment_service.get_payment(session, snap.order_id)
    assert payment.status == PaymentTxStatus.REFUNDED.value


@pytest.mark.asyncio
async def test_capture_is_a_no_op_on_replay(session):
    snap = await _snapshot(session)
    await _authorized_payment(session)

    first = await payment_service.capture_payment(session, snap)
    second = await payment_service.capture_payment(session, snap)

    assert first.status == PaymentTxStatus.SUCCEEDED.value
    assert second.status == PaymentTxStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_capture_still_works_on_a_normal_authorized_payment(session):
    """The guard must not break the path it protects."""
    snap = await _snapshot(session)
    await _authorized_payment(session)

    captured = await payment_service.capture_payment(session, snap)

    assert captured.status == PaymentTxStatus.SUCCEEDED.value


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_checkout_for_an_order_reuses_the_first_payment(session, provider):
    """The ordinary sequential case: one authorize, one row."""
    snap = await _snapshot(session, status="PAYMENT_PENDING")

    first = await payment_service.create_payment_for_order(session, snap, provider=provider)
    second = await payment_service.create_payment_for_order(session, snap, provider=provider)

    assert first.id == second.id
    assert provider.authorize_calls == 1


def _lose_the_race(monkeypatch):
    """Make the existence check miss a payment that is already committed.

    That is precisely the state a losing checkout is in: it read the table before
    the rival's insert landed, and everything it does afterwards is based on a
    snapshot that is already out of date. Faking the stale read is more faithful
    here than threading two requests would be, because the suite's SQLite has a
    single writer and could not run them concurrently anyway.
    """
    real_get_payment = payment_service.get_payment
    calls = {"n": 0}

    async def stale_on_first_call(session, order_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await real_get_payment(session, order_id)

    monkeypatch.setattr(payment_service, "get_payment", stale_on_first_call)


@pytest.mark.asyncio
async def test_losing_a_concurrent_checkout_returns_the_winner_not_a_500(
    session, provider, monkeypatch
):
    """Two checkouts in flight at once, from one double-tapped button.

    The check-then-insert spans ``provider.authorize`` — a network call to a
    payment provider — so the window is wide by construction. Both callers find
    no payment, both authorize (the shared idempotency key is what stops the
    customer being charged twice), and the loser's insert hits the unique
    constraint on order_id. That IntegrityError was unhandled: HTTP 500 on a
    checkout that had in fact succeeded and taken the customer's money.
    """
    snap = await _snapshot(session, status="PAYMENT_PENDING")
    await _authorized_payment(session)          # the winner, already committed
    # Read before the call: the rollback inside it expires every object in the
    # session, so reading snap afterwards would lazy-load and raise.
    order_id = snap.order_id
    _lose_the_race(monkeypatch)

    payment = await payment_service.create_payment_for_order(session, snap, provider=provider)

    assert payment is not None
    assert payment.order_id == order_id
    assert payment.provider_ref == "ref-1"      # the winner's row, not a second one


@pytest.mark.asyncio
async def test_the_loser_gets_no_checkout_url(session, provider, monkeypatch):
    """Only the call that reached the provider owns a hosted-page session.

    Attaching the loser's URL would send the customer to a checkout that is not
    theirs; attaching the winner's is impossible, since this process never saw it.
    """
    snap = await _snapshot(session, status="PAYMENT_PENDING")
    await _authorized_payment(session)
    _lose_the_race(monkeypatch)

    payment = await payment_service.create_payment_for_order(session, snap, provider=provider)

    assert payment_service.checkout_url_of(payment) is None


@pytest.mark.asyncio
async def test_only_one_payment_row_survives_the_race(session, provider, monkeypatch):
    """The unique constraint is the backstop; this confirms it still holds."""
    from sqlalchemy import func, select

    snap = await _snapshot(session, status="PAYMENT_PENDING")
    await _authorized_payment(session)
    order_id = snap.order_id
    _lose_the_race(monkeypatch)

    await payment_service.create_payment_for_order(session, snap, provider=provider)

    count = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.order_id == order_id)
    )
    assert count == 1

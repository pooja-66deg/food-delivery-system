"""Stripe webhook: signature verification and event handling.

Verification is implemented against Stripe's documented scheme rather than
through the SDK, so the endpoint is real security even where the SDK is not
installed — and so it can be tested with a signed fixture.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import AppException
from app import outbox
from app.models import Payment, PaymentTxStatus

logger = logging.getLogger(__name__)

_SEEN_KEY = "stripe:evt:{event_id}"
_SEEN_TTL = 7 * 86400

SUCCEEDED = "payment_intent.succeeded"
FAILED = "payment_intent.payment_failed"
# Hosted Checkout: what settles an order placed through the redirect. The intent
# events above still arrive and are still honoured — whichever lands first marks
# the order paid, and the other finds nothing left to do.
CHECKOUT_COMPLETED = "checkout.session.completed"
CHECKOUT_ASYNC_SUCCEEDED = "checkout.session.async_payment_succeeded"
CHECKOUT_ASYNC_FAILED = "checkout.session.async_payment_failed"

_SETTLES = (SUCCEEDED, CHECKOUT_COMPLETED, CHECKOUT_ASYNC_SUCCEEDED)
_FAILS = (FAILED, CHECKOUT_ASYNC_FAILED)


class WebhookError(AppException):
    """The request could not be trusted. Always a 400 — Stripe retries 5xx."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


def verify_signature(
    payload: bytes,
    header: str | None,
    secret: str | None,
    now: datetime | None = None,
    tolerance_seconds: int = 300,
) -> None:
    """Raise WebhookError unless ``header`` is a valid signature for ``payload``.

    The header looks like ``t=1699999999,v1=<hex>`` and may carry several ``v1``
    values during a secret rotation; any one matching is enough.
    """
    if not secret:
        # Nothing to verify against means nothing can be trusted.
        raise WebhookError("Webhook signing secret is not configured")
    if not header:
        raise WebhookError("Missing signature header")

    timestamp, signatures = _parse(header)
    if timestamp is None or not signatures:
        raise WebhookError("Malformed signature header")

    now = now or datetime.now(timezone.utc)
    if abs(int(now.timestamp()) - timestamp) > tolerance_seconds:
        # Stops a captured request being replayed later.
        raise WebhookError("Signature timestamp outside the tolerance window")

    expected = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise WebhookError("Signature mismatch")


def _parse(header: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None, []
        elif key == "v1":
            signatures.append(value)
    return timestamp, signatures


async def handle_event(session: AsyncSession, redis, event: Mapping[str, Any]) -> str:
    """Apply a verified event. Returns a short outcome for logging/response.

    Every outcome is a success from Stripe's point of view: anything that is not
    2xx is retried, and an event we cannot act on will never succeed on a retry.
    """
    event_id = event.get("id")
    event_type = event.get("type")

    # Redis may be absent — it is shared infrastructure, not a hard dependency.
    # Without it we cannot tell a redelivery from a first delivery, so we process
    # the event: settling is idempotent (the status is set, not incremented), and
    # a duplicate settle is harmless where a dropped one loses a customer's
    # payment. Fail-open is the right direction here, and only here.
    if event_id and redis is not None:
        if not await redis.set(
            _SEEN_KEY.format(event_id=event_id), "1", nx=True, ex=_SEEN_TTL
        ):
            return "duplicate"

    if event_type not in _SETTLES + _FAILS:
        return "ignored"

    obj = event.get("data", {}).get("object", {})
    # A payment row is found by whichever id it currently holds: the Checkout
    # Session while the customer is still on Stripe's page, the PaymentIntent
    # once the session has completed.
    ref = obj.get("id")
    payment = await session.scalar(select(Payment).where(Payment.provider_ref == ref))
    if payment is None:
        # Not an order of ours (or one already cleaned up). Nothing to retry.
        logger.info("[payments:webhook] no payment for reference %s", ref)
        return "unknown"

    if event_type in _FAILS:
        payment.status = PaymentTxStatus.FAILED.value
        await session.commit()
        return "failed"

    if event_type in (CHECKOUT_COMPLETED, CHECKOUT_ASYNC_SUCCEEDED):
        # Point the row at the PaymentIntent — the session id is not something
        # a refund can be issued against.
        intent = obj.get("payment_intent")
        if intent:
            payment.provider_ref = intent
        # A completed session is not always a paid one: a delayed method leaves
        # it unpaid until its own event arrives. Record the intent, wait.
        if obj.get("payment_status") not in (None, "paid", "no_payment_required"):
            await session.commit()
            return "awaiting-payment"

    payment.status = PaymentTxStatus.SUCCEEDED.value
    await session.commit()

    # Imported here rather than at module scope: orders imports payments.
    outbox.record_event(
        session, "payment-events", str(payment.order_id),
        {
            "order_id": payment.order_id,
            "payment_status": "SUCCEEDED",
            "provider": payment.provider,
            "amount": str(payment.amount),
        },
    )
    await session.commit()
    return "paid"

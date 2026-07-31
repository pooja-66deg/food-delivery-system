"""Payment provider abstraction.

The service depends only on the ``PaymentProvider`` protocol, so a real PSP
(Stripe) drops in later by implementing the same two methods — no service
change. ``CODProvider`` is the live MVP provider; ``CardProvider`` is a
deterministic stand-in for an online PSP that the Stripe adapter replaces.
"""
import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    ok: bool
    reference: str | None = None
    status: str = ""


class PaymentProvider(Protocol):
    name: str

    async def authorize(self, amount: Decimal, idempotency_key: str) -> ProviderResult: ...

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult: ...


class CODProvider:
    """Cash on Delivery: nothing is captured up front; cash is collected on
    delivery. Refund is a bookkeeping void because no money moved."""

    name = "COD"

    async def authorize(self, amount: Decimal, idempotency_key: str) -> ProviderResult:
        return ProviderResult(ok=True, reference=None, status="to_collect")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="void")


class CardProvider:
    """Deterministic online-PSP stand-in. A real Stripe adapter implements the
    same interface (create/confirm PaymentIntent, create Refund) keyed by the
    idempotency key."""

    name = "CARD"

    async def authorize(self, amount: Decimal, idempotency_key: str) -> ProviderResult:
        return ProviderResult(ok=True, reference=f"pi_{idempotency_key}", status="authorized")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="refunded")


class StripeProvider:
    """Real online-card provider via Stripe. Used for CARD payments when
    ``STRIPE_SECRET_KEY`` is configured. The blocking SDK calls run in a thread;
    any failure/misconfiguration degrades to ``ok=False`` rather than raising."""

    name = "CARD"

    async def authorize(self, amount: Decimal, idempotency_key: str) -> ProviderResult:
        try:
            import stripe  # optional dependency

            stripe.api_key = settings.stripe_secret_key
            intent = await asyncio.to_thread(
                lambda: stripe.PaymentIntent.create(
                    amount=int(Decimal(amount) * 100),
                    currency="usd",
                    automatic_payment_methods={"enabled": True},
                    idempotency_key=idempotency_key,
                )
            )
            return ProviderResult(ok=True, reference=intent.id, status=intent.status)
        except Exception as exc:  # noqa: BLE001 — never let payment setup crash checkout
            logger.error("[payments:STRIPE] authorize failed: %s", exc)
            return ProviderResult(ok=False, status="error")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        try:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            refund = await asyncio.to_thread(lambda: stripe.Refund.create(payment_intent=reference))
            return ProviderResult(ok=True, reference=reference, status=refund.status)
        except Exception as exc:  # noqa: BLE001
            logger.error("[payments:STRIPE] refund failed: %s", exc)
            return ProviderResult(ok=False, status="error")


def provider_for(method: str) -> PaymentProvider:
    """Resolve the provider for an order's payment method.

    CARD → real Stripe when a secret key is configured, otherwise a deterministic
    stand-in so dev/test flows work without credentials. COD is always local.
    """
    if method == "CARD":
        return StripeProvider() if settings.stripe_secret_key else CardProvider()
    return CODProvider()

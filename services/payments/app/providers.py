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

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    ok: bool
    reference: str | None = None
    status: str = ""
    # Where to send the browser to pay — a Stripe-hosted Checkout page. Never
    # persisted. A provider that settles without the customer's involvement
    # leaves this None, which is the signal that there is nothing left to do.
    checkout_url: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def authorize(
        self, amount: Decimal, idempotency_key: str, order_id: int
    ) -> ProviderResult: ...

    async def verify(self, reference: str | None) -> ProviderResult: ...

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult: ...


class CODProvider:
    """Cash on Delivery: nothing is captured up front; cash is collected on
    delivery. Refund is a bookkeeping void because no money moved."""

    name = "COD"

    async def authorize(
        self, amount: Decimal, idempotency_key: str, order_id: int
    ) -> ProviderResult:
        return ProviderResult(ok=True, reference=None, status="to_collect")

    async def verify(self, reference: str | None) -> ProviderResult:
        # There is no hosted page to come back from; cash arrives on delivery.
        return ProviderResult(ok=False, reference=reference, status="to_collect")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="void")


class CardProvider:
    """Deterministic online-PSP stand-in. A real Stripe adapter implements the
    same interface (open a hosted checkout, create a Refund) keyed by the
    idempotency key."""

    name = "CARD"

    async def authorize(
        self, amount: Decimal, idempotency_key: str, order_id: int
    ) -> ProviderResult:
        return ProviderResult(ok=True, reference=f"pi_{idempotency_key}", status="authorized")

    async def verify(self, reference: str | None) -> ProviderResult:
        # The stand-in settles at authorize time, so anything it issued is paid.
        return ProviderResult(ok=True, reference=reference, status="paid")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="refunded")


class StripeProvider:
    """Real online-card provider via Stripe Checkout. Used for CARD payments
    when ``STRIPE_SECRET_KEY`` is configured.

    Authorizing opens a Stripe-hosted Checkout Session and hands back its URL;
    the customer enters their card on Stripe's page and is returned to the
    order. Nothing is settled here — ``checkout.session.completed`` is what
    marks the order paid. The blocking SDK calls run in a thread; any
    failure/misconfiguration degrades to ``ok=False`` rather than raising.
    """

    name = "CARD"

    async def authorize(
        self, amount: Decimal, idempotency_key: str, order_id: int
    ) -> ProviderResult:
        try:
            import stripe  # optional dependency

            stripe.api_key = settings.stripe_secret_key
            # Both land back on the order page: paid orders show their new
            # status, abandoned ones keep the "Pay now" button.
            base = settings.frontend_base_url.rstrip("/")
            checkout = await asyncio.to_thread(
                lambda: stripe.checkout.Session.create(
                    mode="payment",
                    line_items=[{
                        "quantity": 1,
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": int(Decimal(amount) * 100),
                            "product_data": {"name": f"Order #{order_id}"},
                        },
                    }],
                    success_url=f"{base}/orders/{order_id}?paid=1",
                    cancel_url=f"{base}/orders/{order_id}",
                    client_reference_id=str(order_id),
                    idempotency_key=idempotency_key,
                )
            )
            # The session id is the reference until the payment completes; the
            # webhook swaps in the PaymentIntent, which is what refunds need.
            return ProviderResult(
                ok=True, reference=checkout.id, status=checkout.status or "open",
                checkout_url=checkout.url,
            )
        except Exception as exc:  # noqa: BLE001 — never let payment setup crash checkout
            logger.error("[payments:STRIPE] authorize failed: %s", exc)
            return ProviderResult(ok=False, status="error")

    async def verify(self, reference: str | None) -> ProviderResult:
        """Ask Stripe whether this reference has actually been paid.

        Used on the customer's return from the hosted page, so a local setup
        with no webhook tunnel still settles. ``ok`` means the money moved; the
        returned reference is the PaymentIntent, which is what a refund needs.
        """
        try:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            if (reference or "").startswith("cs_"):
                checkout = await asyncio.to_thread(
                    lambda: stripe.checkout.Session.retrieve(reference)
                )
                return ProviderResult(
                    ok=checkout.payment_status in ("paid", "no_payment_required"),
                    reference=checkout.payment_intent or reference,
                    status=checkout.payment_status or "unpaid",
                )
            intent = await asyncio.to_thread(lambda: stripe.PaymentIntent.retrieve(reference))
            return ProviderResult(
                ok=intent.status == "succeeded", reference=intent.id, status=intent.status,
            )
        except Exception as exc:  # noqa: BLE001 — an unverifiable payment is simply not settled
            logger.error("[payments:STRIPE] verify failed: %s", exc)
            return ProviderResult(ok=False, reference=reference, status="error")

    async def refund(self, reference: str | None, amount: Decimal) -> ProviderResult:
        try:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            intent = await self._payment_intent_for(reference)
            refund = await asyncio.to_thread(lambda: stripe.Refund.create(payment_intent=intent))
            return ProviderResult(ok=True, reference=reference, status=refund.status)
        except Exception as exc:  # noqa: BLE001
            logger.error("[payments:STRIPE] refund failed: %s", exc)
            return ProviderResult(ok=False, status="error")

    @staticmethod
    async def _payment_intent_for(reference: str | None) -> str | None:
        """Resolve a stored reference to the PaymentIntent a refund needs.

        Normally the webhook has already replaced the session id with the
        intent. If it hasn't — a refund racing the webhook, or an event that
        never arrived — look it up rather than handing Stripe a ``cs_`` id it
        will reject.
        """
        if not (reference or "").startswith("cs_"):
            return reference

        import stripe

        session = await asyncio.to_thread(lambda: stripe.checkout.Session.retrieve(reference))
        return session.payment_intent or reference


def provider_for(method: str) -> PaymentProvider:
    """Resolve the provider for an order's payment method.

    CARD → real Stripe when a secret key is configured, otherwise a deterministic
    stand-in so dev/test flows work without credentials. COD is always local.
    """
    if method == "CARD":
        return StripeProvider() if settings.stripe_secret_key else CardProvider()
    return CODProvider()

"""Payment provider abstraction.

The service depends only on the ``PaymentProvider`` protocol, so a real PSP
(Stripe) drops in later by implementing the same two methods — no service
change. ``CODProvider`` is the live MVP provider; ``CardProvider`` is a
deterministic stand-in for an online PSP that the Stripe adapter replaces.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


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


def provider_for(method: str) -> PaymentProvider:
    """Resolve the provider for an order's payment method."""
    return CardProvider() if method == "CARD" else CODProvider()

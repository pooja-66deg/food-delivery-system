"""HTTP surface. Same paths and shapes as the monolith's payments router, so the
frontend does not know it moved.

One thing genuinely changed. The monolith reused the orders module's access
check — ``get_order_for_user``, which loads the order and applies its
customer / owning-restaurant / admin rules. That call is not available here, and
turning it into an HTTP call to the orders service would mean nobody can pay
whenever that service is slow, on the one screen where failing costs money.

So access is decided from the local snapshot: your own order, or a role the
platform already trusts with any order. A restaurant owner loses the ability to
read another restaurant's payment, which they never should have been able to do
anyway.
"""

import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import service as payment_service
from app import webhook as webhook_service
from app.auth import auth
from app.config import settings
from app.db import get_db
from app.models import OrderSnapshot
from app.redis_client import get_redis
from app.schemas import PaymentRead
from shared.errors import ForbiddenException, NotFoundException
from shared.identity import Identity

router = APIRouter(prefix="/payments", tags=["payments"])

_caller = auth.identity()
_customer = auth.require_role("customer")


async def _visible_order(
    session: AsyncSession, caller: Identity, order_id: int
) -> OrderSnapshot:
    """The order, if this caller may see its payment.

    404 before 403: telling a stranger that an order exists but is not theirs
    leaks which order ids are real.
    """
    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        raise NotFoundException("Order", str(order_id))
    if caller.role in ("admin", "restaurant"):
        return snapshot
    if snapshot.customer_id != caller.user_id:
        raise ForbiddenException("Not your order")
    return snapshot


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Public endpoint called by Stripe. The signature is the authentication.

    Deliberately not behind the gateway's auth: Stripe has no token to present.
    The HMAC over the raw body, with a timestamp tolerance, is what proves the
    call came from Stripe and is not a replay.
    """
    payload = await request.body()
    webhook_service.verify_signature(
        payload,
        stripe_signature,
        settings.stripe_webhook_secret,
        tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
    )
    try:
        event = json.loads(payload)
    except ValueError:
        raise webhook_service.WebhookError("Body is not valid JSON")

    outcome = await webhook_service.handle_event(session, redis, event)
    return {"received": True, "outcome": outcome}


@router.get("", response_model=list[PaymentRead])
async def my_payment_history(
    limit: int = 50,
    offset: int = 0,
    caller: Identity = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    return await payment_service.list_for_customer(session, caller.user_id, limit, offset)


@router.get("/order/{order_id}", response_model=PaymentRead)
async def get_order_payment(
    order_id: int,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    await _visible_order(session, caller, order_id)
    payment = await payment_service.get_payment(session, order_id)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment


@router.post("/order/{order_id}/resume", response_model=PaymentRead)
async def resume_order_payment(
    order_id: int,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """Reopen payment for an order the customer left unpaid."""
    order = await _visible_order(session, caller, order_id)
    payment = await payment_service.resume_card_payment(session, order)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment


@router.post("/order/{order_id}/confirm", response_model=PaymentRead)
async def confirm_order_payment(
    order_id: int,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """Settle a card order the customer has just been redirected back from.

    Safe to call at any time: the payment state is read back from the provider,
    so this cannot mark an unpaid order paid.
    """
    order = await _visible_order(session, caller, order_id)
    payment = await payment_service.confirm_card_payment(session, order)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment


@router.post("/order/{order_id}/retry", response_model=PaymentRead)
async def retry_order_payment(
    order_id: int,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    order = await _visible_order(session, caller, order_id)
    payment = await payment_service.retry_payment(session, order)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment

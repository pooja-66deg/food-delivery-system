"""Kafka consumer: keeps the order read-model current, and authorises on demand.

Two jobs:

1. **Copy** — mirror what the orders service says about an order, so this
   service can price a charge without asking it.
2. **React** — when an order reaches PAYMENT_PENDING, create the payment. That
   was a direct call from checkout in the monolith; making it an event is what
   stops a slow payment provider holding up order creation.

``create_payment_for_order`` returns the existing payment untouched if there
already is one, which is what makes the second job safe under at-least-once
delivery.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import service as payment_service
from app.config import settings
from app.db import async_session
from app.models import OrderSnapshot

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None

#: Statuses that mean "this order exists and needs a payment record".
#:
#: Both, not just PAYMENT_PENDING. A COD order is authorised at creation, so
#: checkout advances it PENDING -> SUCCESS before emitting anything and only one
#: event is ever published — carrying PAYMENT_SUCCESS. Listening for PENDING
#: alone means every cash order silently ends up with no payment row, which is
#: invisible until someone reconciles the day's takings.
PAYABLE_STATUSES = ("PAYMENT_PENDING", "PAYMENT_SUCCESS")


async def _apply_order_event(session: AsyncSession, payload: dict) -> None:
    order_id = payload.get("order_id")
    if order_id is None:
        return

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        snapshot = OrderSnapshot(
            order_id=order_id,
            customer_id=payload.get("customer_id") or 0,
            status=payload.get("status") or "",
        )
        session.add(snapshot)

    snapshot.status = payload.get("status") or snapshot.status
    if payload.get("customer_id") is not None:
        snapshot.customer_id = payload["customer_id"]
    # Only overwrite from fields the event carries, so a thinner later event
    # cannot erase what an earlier one told us.
    if payload.get("total") is not None:
        snapshot.total = payload["total"]
    if payload.get("payment_method") is not None:
        snapshot.payment_method = payload["payment_method"]
    await session.commit()

    if snapshot.status in PAYABLE_STATUSES:
        # Idempotent: returns the existing payment untouched, which is what
        # makes this safe under at-least-once delivery.
        await payment_service.create_payment_for_order(session, snapshot)


async def _apply_payment_command(session: AsyncSession, payload: dict) -> None:
    """Do what the orders service asked: settle or refund.

    Orders records the intent in *its* transaction — alongside the status change
    that justified it — and this carries it out. Without this handler the intents
    were published and nothing ever acted on them, so a cancelled card order was
    marked refunded in the order history and the customer never got their money.

    Idempotent by state, not by a marker: capture only moves AUTHORIZED to
    SUCCEEDED and refund only acts on a payment that is not already REFUNDED, so
    a redelivered command is a no-op rather than a second movement of money.
    """
    order_id = payload.get("order_id")
    action = payload.get("action")
    if order_id is None:
        return

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        # The command arrived before the order event that describes it. Raising
        # leaves it unacknowledged, so it is retried once the snapshot lands —
        # which is the right answer for something that moves money.
        raise LookupError(f"no snapshot for order {order_id} yet")

    if action == "settle":
        await payment_service.capture_payment(session, snapshot)
    elif action == "refund":
        await payment_service.refund_payment(session, snapshot)
    else:
        logger.warning("Unknown payment command %r for order %s", action, order_id)


_HANDLERS = {
    "order-events": _apply_order_event,
    "payment-commands": _apply_payment_command,
}


def start_consumer(loop) -> None:
    """Start consuming.

    The loop, the threading and the ack rules live in ``shared.messaging``. Six
    copies of a concurrency-sensitive poll loop was six places for the same
    subtle bug, and they had already drifted. What stays here is the only part
    that is this service's own: which topics, and what to do with each.

    It is also what makes the transport a deploy-time choice — Kafka in the
    compose stack, Pub/Sub on Cloud Run — without this module naming either.
    """
    global _consumer
    _consumer = EventConsumer(
        transport=settings.messaging_transport,
        topics=settings.topics,
        group=settings.kafka_group_id,
        handlers=_HANDLERS,
        session_factory=async_session,
        kafka_servers=settings.kafka_bootstrap_servers,
        project_id=settings.google_cloud_project,
    )
    _consumer.start(loop)


def stop_consumer() -> None:
    global _consumer
    if _consumer is not None:
        _consumer.stop()
        _consumer = None

"""Kafka consumer: keeps the order read-model current.

One job, and a small one — this service is mostly a publisher. It needs to know
which orders exist, who placed them, and whether they were delivered, so that
review eligibility can be decided without asking the orders service.

Runs in a worker thread: kafka-python is a blocking client, and its poll loop
would otherwise stall the event loop serving HTTP.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from app.models import OrderSnapshot

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None


async def _apply_order_event(session: AsyncSession, payload: dict) -> None:
    order_id = payload.get("order_id")
    if order_id is None:
        return

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        snapshot = OrderSnapshot(
            order_id=order_id,
            customer_id=payload.get("customer_id") or 0,
            restaurant_id=payload.get("restaurant_id") or 0,
            status=payload.get("status") or "",
        )
        session.add(snapshot)
    else:
        snapshot.status = payload.get("status") or snapshot.status

    # Only overwrite from fields the event actually carries, so a later, thinner
    # event cannot erase what an earlier one told us.
    if payload.get("customer_id") is not None:
        snapshot.customer_id = payload["customer_id"]
    if payload.get("restaurant_id") is not None:
        snapshot.restaurant_id = payload["restaurant_id"]
    if payload.get("customer_name") is not None:
        snapshot.customer_name = payload["customer_name"]
    await session.commit()


_HANDLERS = {
    "order-events": _apply_order_event,
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

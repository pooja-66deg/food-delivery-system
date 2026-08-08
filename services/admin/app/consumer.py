"""Kafka consumer: the console's entire data supply.

Unlike every other service, admin consumes broadly on purpose — it reports on
the whole platform, so it subscribes to the whole platform. That is the right
answer here and a smell anywhere else.

Every handler is a plain upsert keyed on the publisher's id, which makes
redelivery harmless: applying the same event twice produces the same row.

Runs in a worker thread: kafka-python is a blocking client, and its poll loop
would otherwise stall the event loop serving HTTP.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from app.models import OrderRow, RestaurantRow, UserRow

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _apply_order_event(session: AsyncSession, payload: dict) -> None:
    order_id = payload.get("order_id")
    if order_id is None:
        return
    row = await session.get(OrderRow, order_id)
    if row is None:
        row = OrderRow(
            id=order_id,
            customer_id=payload.get("customer_id") or 0,
            restaurant_id=payload.get("restaurant_id") or 0,
            created_at=_now(),
        )
        session.add(row)
    # Status is overwritten, not appended: the console reports where orders are,
    # and the orders service keeps the transition log for anyone who wants the
    # history.
    row.status = payload.get("status") or row.status
    if payload.get("customer_id") is not None:
        row.customer_id = payload["customer_id"]
    if payload.get("restaurant_id") is not None:
        row.restaurant_id = payload["restaurant_id"]
    if payload.get("payment_status") is not None:
        row.payment_status = payload["payment_status"]
    if payload.get("total") is not None:
        row.total = payload["total"]
    await session.commit()


async def _apply_user_event(session: AsyncSession, payload: dict) -> None:
    """Name, role and status. Contact details arrive separately."""
    user_id = payload.get("user_id")
    if user_id is None:
        return
    row = await session.get(UserRow, user_id)
    if row is None:
        row = UserRow(id=user_id, created_at=_now())
        session.add(row)
    for field in ("first_name", "last_name", "role"):
        if payload.get(field) is not None:
            setattr(row, field, payload[field])
    if payload.get("is_active") is not None:
        row.is_active = bool(payload["is_active"])
    await session.commit()


async def _apply_contact_event(session: AsyncSession, payload: dict) -> None:
    """Email and phone, from the restricted topic.

    An operator looking a customer up needs to recognise them, which is this
    service's reason to be on that topic at all.
    """
    user_id = payload.get("user_id")
    if user_id is None:
        return
    row = await session.get(UserRow, user_id)
    if row is None:
        row = UserRow(id=user_id, created_at=_now())
        session.add(row)
    if payload.get("email") is not None:
        row.email = payload["email"]
    if payload.get("phone") is not None:
        row.phone = payload["phone"]
    await session.commit()


async def _apply_restaurant_event(session: AsyncSession, payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    if restaurant_id is None:
        return
    row = await session.get(RestaurantRow, restaurant_id)
    if row is None:
        row = RestaurantRow(id=restaurant_id, created_at=_now())
        session.add(row)
    if payload.get("name") is not None:
        row.name = payload["name"]
    if payload.get("owner_id") is not None:
        row.owner_id = payload["owner_id"]
    await session.commit()


_HANDLERS = {
    "order-events": _apply_order_event,
    "user-events": _apply_user_event,
    "user-contact-events": _apply_contact_event,
    "restaurant-events": _apply_restaurant_event,
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

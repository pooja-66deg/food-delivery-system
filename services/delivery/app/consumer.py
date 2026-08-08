"""Kafka consumer: keeps the read-models current and reacts to order events.

Two jobs, and they are worth separating in your head:

1. **Copy** — an order or a driver changed somewhere else, so update the local
   snapshot. Pure bookkeeping, always safe to repeat.
2. **React** — an order became ready for pickup, so assign a driver. A real
   action, and the one that has to be idempotent, because an at-least-once
   stream will hand it to us twice.

``assign_for_order`` returns the existing delivery untouched if there already is
one, which is what makes the second job safe.

Runs in a worker thread: kafka-python is a blocking client, and its poll loop
would otherwise stall the event loop serving HTTP.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.config import settings
from app.db import async_session
from app.models import Driver, OrderSnapshot, RestaurantSnapshot
from app.redis_client import get_redis

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None

#: The one status that means "a driver is needed now".
READY_FOR_PICKUP = "READY_FOR_PICKUP"


async def _apply_order_event(session: AsyncSession, payload: dict) -> None:
    """Update the order snapshot, and assign a driver if it just became ready."""
    order_id = payload.get("order_id")
    if order_id is None:
        return

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        snapshot = OrderSnapshot(order_id=order_id, customer_id=payload.get("customer_id") or 0)
        session.add(snapshot)

    snapshot.status = payload.get("status") or snapshot.status or ""
    if payload.get("customer_id") is not None:
        snapshot.customer_id = payload["customer_id"]
    if payload.get("restaurant_id") is not None:
        snapshot.restaurant_id = payload["restaurant_id"]
    # Coordinates only overwrite when the event actually carries them, so a
    # later event with a thinner payload cannot erase what an earlier one knew.
    for field in (
        "restaurant_latitude",
        "restaurant_longitude",
        "destination_latitude",
        "destination_longitude",
    ):
        if payload.get(field) is not None:
            setattr(snapshot, field, payload[field])
    await session.commit()

    if snapshot.status == READY_FOR_PICKUP:
        redis = await get_redis()
        await service.assign_for_order(session, order_id, redis=redis)


async def _apply_user_event(session: AsyncSession, payload: dict) -> None:
    """Keep the driver roster current.

    Only drivers are copied. A service that mirrored every user would be holding
    personal data it has no use for, and would have to care about every change
    to any of them.
    """
    user_id = payload.get("user_id") or payload.get("id")
    if user_id is None or payload.get("role") != "driver":
        return

    driver = await session.get(Driver, user_id)
    if driver is None:
        driver = Driver(id=user_id)
        session.add(driver)
    if payload.get("first_name") is not None:
        driver.first_name = payload["first_name"]
    if payload.get("last_name") is not None:
        driver.last_name = payload["last_name"]
    if payload.get("is_active") is not None:
        driver.is_active = bool(payload["is_active"])
    await session.commit()


async def _apply_restaurant_event(session: AsyncSession, payload: dict) -> None:
    """Keep the owner roster current.

    An owner id and nothing else: it answers "may this caller reassign the
    driver on this order?" and that is all this service asks about a restaurant.
    """
    restaurant_id = payload.get("restaurant_id")
    owner_id = payload.get("owner_id")
    if restaurant_id is None or owner_id is None:
        return
    snapshot = await session.get(RestaurantSnapshot, restaurant_id)
    if snapshot is None:
        snapshot = RestaurantSnapshot(restaurant_id=restaurant_id, owner_id=owner_id)
        session.add(snapshot)
    else:
        snapshot.owner_id = owner_id
    await session.commit()


_HANDLERS = {
    "order-events": _apply_order_event,
    "user-events": _apply_user_event,
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

"""Kafka consumer: keeps this service's read-models current, and reacts.

Orders consumes more than anything else, because it is the service everything
else reports back to:

    payment-events    money moved -> advance the order
    delivery-events   driver picked up / delivered -> advance the order
    address-events    a delivery address exists or moved -> checkout can use it
    restaurant-events who owns a restaurant -> the owner check on every action
    user-events       a customer's display name -> the byline on a review

The two that *act* — payments and delivery — go through the same state machine
the API does, so an event cannot make a transition a person could not.

Runs in a worker thread: kafka-python is a blocking client, and its poll loop
would otherwise stall the event loop serving HTTP.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.config import settings
from app.db import async_session
from app.models import (
    AddressSnapshot,
    CustomerSnapshot,
    OrderStatus,
    RestaurantSnapshot,
)

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None


def _display_name(first: str | None, last: str | None) -> str:
    """"Alex R." — the same shape the monolith showed, built once here."""
    first = (first or "").strip()
    last = (last or "").strip()
    if not first:
        return ""
    return f"{first} {last[0]}." if last else first


async def _apply_payment_event(session: AsyncSession, payload: dict) -> None:
    """Money moved. Advance the order the way ``mark_paid`` used to."""
    order_id = payload.get("order_id")
    if order_id is None or payload.get("payment_status") != "SUCCEEDED":
        return
    # Idempotent: an order already past payment is returned untouched, which is
    # what makes an at-least-once redelivery harmless.
    await service.mark_paid(session, order_id)


async def _apply_delivery_event(session: AsyncSession, payload: dict) -> None:
    """A driver picked up or delivered. Advance the order to match."""
    order_id = payload.get("order_id")
    status = payload.get("status")
    if order_id is None:
        return

    target = {
        "PICKED_UP": OrderStatus.OUT_FOR_DELIVERY,
        "DELIVERED": OrderStatus.DELIVERED,
    }.get(status)
    if target is None:
        return  # ASSIGNED / ACCEPTED change nothing about the order itself

    try:
        await service.driver_advance(session, order_id, target)
    except Exception as exc:  # noqa: BLE001
        # A transition the state machine refuses is not a transport failure —
        # redelivering it forever would block the topic. Log and move on.
        logger.warning("Delivery event for order %s not applied: %s", order_id, exc)
        await session.rollback()


async def _apply_address_event(session: AsyncSession, payload: dict) -> None:
    address_id = payload.get("address_id")
    if address_id is None:
        return
    snapshot = await session.get(AddressSnapshot, address_id)
    if snapshot is None:
        snapshot = AddressSnapshot(
            address_id=address_id, user_id=payload.get("user_id") or 0
        )
        session.add(snapshot)
    if payload.get("user_id") is not None:
        snapshot.user_id = payload["user_id"]
    snapshot.city = payload.get("city") or ""
    # Assigned even when null: a re-geocode that failed clears the old point,
    # and keeping a stale one would route a delivery to the wrong place.
    snapshot.latitude = payload.get("latitude")
    snapshot.longitude = payload.get("longitude")
    await session.commit()


async def _apply_restaurant_event(session: AsyncSession, payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    if restaurant_id is None:
        return
    snapshot = await session.get(RestaurantSnapshot, restaurant_id)
    if snapshot is None:
        snapshot = RestaurantSnapshot(
            restaurant_id=restaurant_id, owner_id=payload.get("owner_id") or 0
        )
        session.add(snapshot)
    if payload.get("owner_id") is not None:
        snapshot.owner_id = payload["owner_id"]
    if payload.get("name") is not None:
        snapshot.name = payload["name"]
    await session.commit()


async def _apply_user_event(session: AsyncSession, payload: dict) -> None:
    """Copy what an order event has to carry about its customer.

    Only customers, and only their display name: a driver or an owner never
    appears on an order as the person being notified.
    """
    user_id = payload.get("user_id")
    if user_id is None or payload.get("role") != "customer":
        return
    snapshot = await session.get(CustomerSnapshot, user_id)
    if snapshot is None:
        snapshot = CustomerSnapshot(user_id=user_id)
        session.add(snapshot)
    snapshot.display_name = _display_name(
        payload.get("first_name"), payload.get("last_name")
    )
    await session.commit()


_HANDLERS = {
    "payment-events": _apply_payment_event,
    "delivery-events": _apply_delivery_event,
    "address-events": _apply_address_event,
    "restaurant-events": _apply_restaurant_event,
    "user-events": _apply_user_event,
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

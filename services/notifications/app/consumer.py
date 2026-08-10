"""Kafka consumer: turns order status events into notifications.

This is the whole reason the service can fail alone. Orders does not call it —
orders writes an event and commits. If this consumer is not running, events wait
in Kafka; when it starts again it reads from its last committed offset and the
backlog is delivered. Nothing upstream noticed.

Runs in a worker thread: kafka-python is a blocking client, and its poll loop
would otherwise stall the event loop serving HTTP requests.
"""

import logging


from app import service, templates
from app.config import settings
from app.db import async_session
from app.models import Channel, Contact, Notification
from app.schemas import OrderStatusEvent

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None


async def _handle_order(session, payload: dict) -> None:
    await service.handle_order_status(session, OrderStatusEvent(**payload))


async def _handle_contact(session, payload: dict) -> None:
    """Keep the contacts read-model current.

    Only this service subscribes to the topic that carries these, so an address
    reaches one database rather than every consumer of ``user-events``.
    """
    user_id = payload.get("user_id")
    if user_id is None:
        return
    contact = await session.get(Contact, user_id)
    if contact is None:
        contact = Contact(user_id=user_id)
        session.add(contact)
    if payload.get("email") is not None:
        contact.email = payload["email"]
    if payload.get("phone") is not None:
        contact.phone = payload["phone"]
    await session.commit()


async def _handle_direct(session, payload: dict) -> None:
    """A one-off message another service asked us to send.

    "The restaurant replied to your review", and anything else that does not fit
    an existing event. The caller names the channel and the address when it has
    one — it may be an address that belongs to no user at all — and otherwise
    this is an in-app feed row.

    This stayed generic when the users service stopped producing on this topic.
    Its OTP, password-reset and verification mails were the original callers;
    the shape outlived them because it never encoded what the message was for.
    """
    user_id = payload.get("user_id")
    channel = payload.get("channel")
    message = payload.get("message") or ""

    if channel and payload.get("to"):
        from app import senders
        from app.models import Notification

        try:
            ok = await senders.dispatch(
                channel, payload["to"], message, payload.get("subject")
            )
        except Exception as exc:  # noqa: BLE001 — a raising sender is a failed send
            logger.error("[notify] %s send raised: %s", channel, exc)
            ok = False
        session.add(
            Notification(
                user_id=user_id or 0,
                channel=channel,
                type=payload.get("type") or "account",
                message=message,
                order_id=payload.get("order_id"),
                delivered=ok,
            )
        )
    elif user_id is not None:
        service.add_notification(
            session, user_id, payload.get("type") or "info", message,
            payload.get("order_id"),
        )
    await session.commit()


async def _handle_restaurant(session, payload: dict) -> None:
    """Mail a restaurant owner the operator's decision on their venue.

    This service is the only one that can send it. The restaurants service makes
    the decision but holds no addresses — deliberately, it does not subscribe to
    ``user-contact-events`` — and the owner cannot be told in the app, because
    the whole point of the state being decided is that they are locked out of it
    until it is. So the decision travels as a status and the address is resolved
    here, from the contacts read-model.

    Idempotency is the caller's problem and it is unsolved here on purpose: a
    redelivered event sends a second identical mail. A duplicate "you are
    approved" is a far better failure than tracking send state to avoid it, and
    the alternative — acknowledging before sending — loses the mail outright.
    """
    owner_id = payload.get("owner_id")
    status = payload.get("approval_status")
    if owner_id is None or status is None:
        return

    wording = templates.restaurant_decision(status, payload.get("name") or "Your restaurant")
    if wording is None:
        return  # a status with no decision to announce — see RESTAURANT_DECISION
    subject, body = wording

    contact = await session.get(Contact, owner_id)
    if contact is None or not contact.email:
        # The address arrives on its own topic and may simply not have landed
        # yet. Nothing is retried: an approval whose mail was missed is visible
        # the moment the owner tries to sign in, which now works.
        logger.warning("[notify] no email on file for owner %s", owner_id)
        return

    from app import senders

    try:
        ok = await senders.dispatch(Channel.EMAIL.value, contact.email, body, subject)
    except Exception as exc:  # noqa: BLE001 — a raising sender is a failed send
        logger.error("[notify] restaurant decision send raised: %s", exc)
        ok = False

    session.add(
        Notification(
            user_id=owner_id,
            channel=Channel.EMAIL.value,
            type=f"restaurant.{status}",
            message=body,
            delivered=ok,
        )
    )
    await session.commit()


_HANDLERS = {
    "order-events": _handle_order,
    "notification-events": _handle_direct,
    "user-contact-events": _handle_contact,
    "restaurant-events": _handle_restaurant,
}


def start_consumer(loop) -> None:
    """Start consuming.

    The loop, the threading and the ack rules live in ``shared.messaging``. What
    stays here is the only part that is this service's own: which topics, and
    what to do with each — and it is what makes the transport a deploy-time
    choice, Kafka in compose and Pub/Sub on Cloud Run.
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

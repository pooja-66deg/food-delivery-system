"""Recording and sending notifications.

Nothing here loads a ``User``: there is no users table in this database, and
calling the users service per status change would make this service inherit that
one's downtime.

Where to send comes from the local ``contacts`` read-model instead — this is the
service that sends, so this is where an address belongs. Handling an event stays
a purely local operation, and no other service ends up holding a copy of somebody
else's address it never uses.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import preferences, senders, templates
from app.models import Channel, Contact, Notification
from app.schemas import OrderStatusEvent

logger = logging.getLogger(__name__)


def add_notification(
    session: AsyncSession, user_id: int, type_: str, message: str, order_id: int | None = None
) -> Notification:
    """Append an in-app feed row. Caller commits."""
    row = Notification(
        user_id=user_id,
        channel=Channel.LOG.value,
        type=type_,
        message=message,
        order_id=order_id,
        delivered=True,
    )
    session.add(row)
    return row


async def handle_order_status(session: AsyncSession, event: OrderStatusEvent) -> list[Notification]:
    """Everything one order status change produces: the feed row, then the sends.

    Never raises. A notification that cannot be sent must not be able to fail the
    event — the order it describes already happened, and failing here would make
    the consumer redeliver an event whose feed row is already written.
    """
    rows: list[Notification] = []

    # The in-app feed gets every status; the outbound channels deliberately do
    # not (see templates: nine emails per order gets filtered as spam).
    rows.append(
        add_notification(
            session,
            event.customer_id,
            f"order.{event.status}",
            templates.short_copy(event.status),
            event.order_id,
        )
    )

    prefs = await preferences.get_preferences(session, event.customer_id)
    for channel in templates.channels_for(event.status):
        if not preferences.allows(prefs, channel):
            continue
        rendered = templates.render(channel, event.status, event.order_id)
        for recipient in await _recipients(session, channel, event):
            rows.append(await _send_one(session, event, rendered, recipient))

    await session.commit()
    return rows


async def _recipients(
    session: AsyncSession, channel: Channel, event: OrderStatusEvent
) -> list[str]:
    """Where a channel sends for this user.

    All of it local: push targets are registered here, and email/SMS addresses
    come from the contacts read-model. An empty list is a silent skip, not a
    failure — a user we cannot reach on a channel simply is not reached on it.
    """
    if channel is Channel.PUSH:
        return await preferences.device_tokens(session, event.customer_id)
    if channel in (Channel.EMAIL, Channel.SMS):
        contact = await session.get(Contact, event.customer_id)
        if contact is None:
            return []
        address = contact.email if channel is Channel.EMAIL else contact.phone
        return [address] if address else []
    return []


async def _send_one(
    session: AsyncSession, event: OrderStatusEvent, rendered: templates.Rendered, recipient: str
) -> Notification:
    """Dispatch one message and record the attempt. Caller commits."""
    try:
        ok = await senders.dispatch(rendered.channel, recipient, rendered.body, rendered.subject)
    except Exception as exc:  # noqa: BLE001 — a raising sender is still a failed send
        logger.error("[notify] %s send raised for order %s: %s", rendered.channel, event.order_id, exc)
        ok = False

    row = Notification(
        user_id=event.customer_id,
        channel=rendered.channel,
        type=f"order.{event.status}",
        message=rendered.body,
        order_id=event.order_id,
        delivered=ok,
    )
    session.add(row)
    return row


async def list_for_user(session: AsyncSession, user_id: int, limit: int = 50) -> list[Notification]:
    """The user's in-app feed, newest first.

    LOG rows only: the outbound rows are a delivery audit trail, and showing them
    here would repeat every message up to three times in the feed.
    """
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id, Notification.channel == Channel.LOG.value)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def list_deliveries(
    session: AsyncSession, user_id: int, limit: int = 50
) -> list[Notification]:
    """The outbound attempts for a user — what we tried to send, and whether it
    landed. The complement of the in-app feed."""
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id, Notification.channel != Channel.LOG.value)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))

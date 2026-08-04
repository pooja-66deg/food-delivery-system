"""Notification dispatch: the in-app feed, plus outbound email / SMS / push."""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications import preferences, senders, templates
from src.modules.notifications.models import Channel, Notification
from src.modules.users.models import User

logger = logging.getLogger(__name__)


def add_notification(
    session: AsyncSession, user_id: int, type_: str, message: str, order_id: int | None = None
) -> None:
    """Append an in-app notification to the current transaction (caller commits)."""
    session.add(
        Notification(user_id=user_id, channel=Channel.LOG.value, type=type_,
                     message=message, order_id=order_id)
    )


def notify_order_status(session: AsyncSession, order) -> None:
    """Queue the customer's in-app notification for the order's current status.

    Stays inside the caller's transaction and does not commit, so the feed row
    lands atomically with the status change it describes. Outbound copies are a
    separate, post-commit step — see ``deliver_order_status``.
    """
    add_notification(
        session, order.customer_id, f"order.{order.status}",
        templates.short_copy(order.status), order.id,
    )


async def deliver_order_status(session: AsyncSession, order) -> list[Notification]:
    """Send the outbound copies of a status change. Returns the delivery rows.

    **Must run after the status change is committed.** Two reasons: a provider
    call has no business holding a database transaction open, and a message
    already sent cannot be rolled back — so we would rather send nothing for a
    change that failed to persist than announce one that did not.

    Never raises. Every sender already degrades to False rather than throwing,
    and a notification that cannot be sent must not undo a delivered order.
    """
    channels = templates.channels_for(order.status)
    if not channels:
        return []

    customer = await session.get(User, order.customer_id)
    if customer is None:  # deleted mid-flight; nothing to notify
        return []

    prefs = await preferences.get_preferences(session, order.customer_id)
    rows: list[Notification] = []
    for channel in channels:
        if not preferences.allows(prefs, channel):
            continue
        rendered = templates.render(channel, order.status, order.id)
        for recipient in await _recipients(session, channel, customer):
            rows.append(await _send_one(session, order, rendered, recipient))

    if rows:
        await session.commit()
    return rows


async def _recipients(session: AsyncSession, channel: Channel, customer: User) -> list[str]:
    """Where a channel sends for this user.

    Push fans out across every registered device; email and SMS have exactly one
    address each. An empty list means the user has nothing registered for that
    channel, which is a silent skip rather than a failure.
    """
    if channel is Channel.PUSH:
        return await preferences.device_tokens(session, customer.id)
    if channel is Channel.EMAIL:
        return [customer.email] if customer.email else []
    if channel is Channel.SMS:
        return [customer.phone] if customer.phone else []
    return []


async def _send_one(
    session: AsyncSession, order, rendered: templates.Rendered, recipient: str
) -> Notification:
    """Dispatch one message and record the attempt. Caller commits."""
    try:
        ok = await senders.dispatch(rendered.channel, recipient, rendered.body, rendered.subject)
    except Exception as exc:  # noqa: BLE001 — a raising sender is still a failed send
        logger.error("[notify] %s send raised for order %s: %s", rendered.channel, order.id, exc)
        ok = False

    row = Notification(
        user_id=order.customer_id,
        channel=rendered.channel,
        type=f"order.{order.status}",
        message=rendered.body,
        order_id=order.id,
        delivered=ok,
    )
    session.add(row)
    return row


async def list_for_user(session: AsyncSession, user_id: int, limit: int = 50) -> list[Notification]:
    """The user's in-app feed, newest first.

    Restricted to LOG rows: the outbound email/SMS/push rows are a delivery
    audit trail, and showing them here would repeat every message up to three
    times in the customer's feed.
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

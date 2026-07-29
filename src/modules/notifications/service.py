"""Notification dispatch (log channel) + order-status alerts."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.models import Channel, Notification

# Human-readable copy per order status.
_STATUS_MESSAGE = {
    "PAYMENT_SUCCESS": "Your order is confirmed and awaiting the restaurant.",
    "RESTAURANT_ACCEPTED": "The restaurant accepted your order.",
    "PREPARING": "Your order is being prepared.",
    "READY_FOR_PICKUP": "Your order is ready and awaiting a driver.",
    "OUT_FOR_DELIVERY": "Your order is on the way!",
    "DELIVERED": "Your order has been delivered. Enjoy!",
    "COMPLETED": "Your order is complete.",
    "CANCELLED": "Your order was cancelled.",
    "REJECTED": "The restaurant could not accept your order.",
}


def add_notification(
    session: AsyncSession, user_id: int, type_: str, message: str, order_id: int | None = None
) -> None:
    """Append a notification row to the current transaction (caller commits)."""
    session.add(
        Notification(user_id=user_id, channel=Channel.LOG.value, type=type_,
                     message=message, order_id=order_id)
    )


def notify_order_status(session: AsyncSession, order) -> None:
    """Queue a customer notification for the order's current status (no commit)."""
    message = _STATUS_MESSAGE.get(order.status, f"Order status: {order.status}")
    add_notification(session, order.customer_id, f"order.{order.status}", message, order.id)


async def list_for_user(session: AsyncSession, user_id: int, limit: int = 50) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))

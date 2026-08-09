"""Outbound message copy per order status, and which channels each status uses.

Two things live here so they cannot drift apart: what we say, and where we say
it. The in-app feed shows every status; the outbound channels deliberately do
not, because a platform that emails nine times per order gets filtered as spam
and an SMS per step is somebody's money.

Channel policy:

- **PUSH** — every status. It is free, silent, and the closest thing to the live
  timeline the customer is watching.
- **SMS** — only what you need to know while away from the app: the driver is
  coming, it arrived, or it is not coming at all.
- **EMAIL** — only what belongs in a paper trail: the confirmation, and the
  final outcome.
"""
from dataclasses import dataclass

from app.models import Channel

# Short copy — the in-app feed row, and the body of an SMS or push, where there
# is no room for more than the fact itself.
STATUS_COPY = {
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

# Email subject per status. A status absent here is not emailed at all, which is
# why the map is shorter than STATUS_COPY.
EMAIL_SUBJECT = {
    "PAYMENT_SUCCESS": "Order #{order_id} confirmed",
    "DELIVERED": "Order #{order_id} delivered",
    "CANCELLED": "Order #{order_id} cancelled",
    "REJECTED": "Order #{order_id} could not be accepted",
}

_SMS_STATUSES = frozenset({"OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED", "REJECTED"})

# An operator's decision on a restaurant registration, worded for its owner.
#
# Email rather than an in-app row, and it is the one place that choice is not
# about preference: the owner's account is inactive until they are approved, so
# they cannot sign in to read a feed. The mail is the only channel that reaches
# somebody the platform is currently keeping out.
#
# "pending" is deliberately absent. It is the status a registration already has
# when it is created, and mailing "we have received it" on every republish of a
# restaurant — a rename, a kitchen closing — would be noise about nothing.
RESTAURANT_DECISION = {
    "approved": (
        "Your restaurant is approved",
        "{name} has been approved. You can now sign in and start setting up "
        "your menu — customers will see you as soon as you open the kitchen.",
    ),
    "rejected": (
        "About your restaurant registration",
        "{name} was not approved, so it will not appear to customers and you "
        "cannot sign in yet. If you think this is a mistake, reply to this "
        "email and we will take another look.",
    ),
}


def restaurant_decision(status: str, name: str) -> tuple[str, str] | None:
    """Subject and body for an approval decision, or None if it is not one worth
    mailing about. Callers treat None as "nothing to send"."""
    wording = RESTAURANT_DECISION.get(status)
    if wording is None:
        return None
    subject, body = wording
    return subject, body.format(name=name)


# The in-app feed is written separately (it is the notification row itself), so
# LOG never appears here.
_CHANNELS_BY_STATUS = {
    status: tuple(
        channel
        for channel, included in (
            (Channel.PUSH, True),
            (Channel.SMS, status in _SMS_STATUSES),
            (Channel.EMAIL, status in EMAIL_SUBJECT),
        )
        if included
    )
    for status in STATUS_COPY
}


@dataclass(frozen=True)
class Rendered:
    """One status change, worded for one channel."""

    channel: str
    subject: str | None
    body: str


def short_copy(status: str) -> str:
    """The in-app / SMS / push wording for a status.

    An unknown status still produces something a human can read rather than a
    blank notification, because a new status must never silence the feed.
    """
    return STATUS_COPY.get(status, f"Order status: {status}")


def channels_for(status: str) -> tuple[Channel, ...]:
    """Outbound channels this status is worth sending on."""
    return _CHANNELS_BY_STATUS.get(status, ())


def render(channel: Channel, status: str, order_id: int) -> Rendered:
    """Word a status change for one channel.

    Email gets a subject and a body that names the order; SMS and push get the
    short copy prefixed with the order number, because they arrive with no
    surrounding context to say which order they are about.
    """
    copy = short_copy(status)
    if channel is Channel.EMAIL:
        subject = EMAIL_SUBJECT.get(status, "Order update").format(order_id=order_id)
        body = f"{copy}\n\nOrder #{order_id}"
        return Rendered(channel=channel.value, subject=subject, body=body)
    return Rendered(channel=channel.value, subject=None, body=f"Order #{order_id}: {copy}")

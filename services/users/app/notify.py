"""Asking the notifications service to send something.

One caller now: the password-reset email. The monolith called ``senders.dispatch``
directly and waited for SendGrid to answer, which was wrong once the split
exists — this service would own outbound delivery it no longer owns, and a slow
provider would hold up the request.

So it records an event instead. The request commits, the relay publishes, the
notifications service sends. If that service is down the mail goes out when it
returns, rather than the reset failing.

The one thing to be honest about: delivery is asynchronous, so the link arrives
shortly after the response rather than before it. That is already true of every
email that goes through a provider queue.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import outbox

TOPIC = "notification-events"


def send(
    session: AsyncSession,
    *,
    channel: str,
    to: str,
    message: str,
    subject: Optional[str] = None,
    user_id: Optional[int] = None,
    type_: str = "account",
) -> None:
    """Queue an outbound message. Recorded in the caller's transaction.

    ``to`` is carried explicitly rather than looked up by the consumer: a
    password reset goes to an address that may not belong to a user at all, and
    the notifications service has no users table to resolve one anyway.
    """
    outbox.record_event(
        session,
        TOPIC,
        str(user_id) if user_id is not None else None,
        {
            "user_id": user_id,
            "type": type_,
            "channel": channel,
            "to": to,
            "subject": subject,
            "message": message,
        },
    )

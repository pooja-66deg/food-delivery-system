"""Notification channel senders.

The in-app **LOG** channel is real (the notification row is the user's feed).
SMS / EMAIL / PUSH are swappable adapters with a log-only transport here — wire
Twilio / SendGrid / FCM in the marked spots when credentials are configured.
The dispatcher depends only on the ``NotificationSender`` protocol.
"""
import asyncio
import logging
from typing import Protocol

from src.config import settings

logger = logging.getLogger(__name__)


class NotificationSender(Protocol):
    channel: str

    async def send(self, to: str, message: str) -> bool: ...


class LogSender:
    channel = "LOG"

    async def send(self, to: str, message: str) -> bool:
        logger.info("[notify:LOG] to=%s :: %s", to, message)
        return True


class SmsSender:
    channel = "SMS"

    async def send(self, to: str, message: str) -> bool:
        """Send via Twilio when credentials are configured; otherwise log.

        The Twilio SDK is an optional dependency — if it isn't installed or the
        send fails, we log and report failure rather than raising."""
        sid, token, from_ = (
            settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number,
        )
        if sid and token and from_:
            try:
                from twilio.rest import Client  # optional dependency

                client = Client(sid, token)
                await asyncio.to_thread(
                    lambda: client.messages.create(to=to, from_=from_, body=message)
                )
                logger.info("[notify:SMS] sent via Twilio to %s", to)
                return True
            except Exception as exc:  # noqa: BLE001 — never let SMS break the flow
                logger.error("[notify:SMS] Twilio send failed: %s", exc)
                return False
        logger.info("[notify:SMS] (no Twilio config) to=%s :: %s", to, message)
        return True


class EmailSender:
    channel = "EMAIL"

    async def send(self, to: str, message: str) -> bool:
        # TODO: integrate SendGrid/SES here. Stubbed to a log.
        logger.info("[notify:EMAIL] to=%s :: %s", to, message)
        return True


class PushSender:
    channel = "PUSH"

    async def send(self, to: str, message: str) -> bool:
        # TODO: integrate FCM here. Stubbed to a log.
        logger.info("[notify:PUSH] to=%s :: %s", to, message)
        return True


_SENDERS = {s.channel: s for s in (LogSender(), SmsSender(), EmailSender(), PushSender())}


def get_sender(channel: str) -> NotificationSender:
    """Resolve a sender by channel; falls back to the in-app LOG channel."""
    return _SENDERS.get(channel, _SENDERS["LOG"])


async def dispatch(channel: str, to: str, message: str) -> bool:
    """Send ``message`` to ``to`` over ``channel`` (best-effort)."""
    return await get_sender(channel).send(to, message)

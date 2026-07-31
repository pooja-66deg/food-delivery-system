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
        """Send via SendGrid when configured; otherwise log. Failures degrade to
        False rather than raising."""
        key, sender = settings.sendgrid_api_key, settings.sendgrid_from_email
        if key and sender:
            try:
                import sendgrid  # optional dependency
                from sendgrid.helpers.mail import Mail

                client = sendgrid.SendGridAPIClient(key)
                mail = Mail(from_email=sender, to_emails=to, subject="Order update",
                            plain_text_content=message)
                await asyncio.to_thread(lambda: client.send(mail))
                logger.info("[notify:EMAIL] sent via SendGrid to %s", to)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("[notify:EMAIL] SendGrid send failed: %s", exc)
                return False
        logger.info("[notify:EMAIL] (no provider) to=%s :: %s", to, message)
        return True


class PushSender:
    channel = "PUSH"

    async def send(self, to: str, message: str) -> bool:
        """Send a push via FCM (legacy HTTP) when a server key is configured;
        otherwise log. ``to`` is a device token."""
        key = settings.fcm_server_key
        if key:
            try:
                import httpx  # already a dependency

                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        "https://fcm.googleapis.com/fcm/send",
                        headers={"Authorization": f"key={key}", "Content-Type": "application/json"},
                        json={"to": to, "notification": {"title": "Order update", "body": message}},
                    )
                resp.raise_for_status()
                logger.info("[notify:PUSH] sent via FCM to %s", to)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("[notify:PUSH] FCM send failed: %s", exc)
                return False
        logger.info("[notify:PUSH] (no provider) to=%s :: %s", to, message)
        return True


_SENDERS = {s.channel: s for s in (LogSender(), SmsSender(), EmailSender(), PushSender())}


def get_sender(channel: str) -> NotificationSender:
    """Resolve a sender by channel; falls back to the in-app LOG channel."""
    return _SENDERS.get(channel, _SENDERS["LOG"])


async def dispatch(channel: str, to: str, message: str) -> bool:
    """Send ``message`` to ``to`` over ``channel`` (best-effort)."""
    return await get_sender(channel).send(to, message)

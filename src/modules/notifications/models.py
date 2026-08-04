"""Notification model — a delivery log per architecture (log channel for MVP)."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Channel(str, Enum):
    LOG = "LOG"
    PUSH = "PUSH"
    SMS = "SMS"
    EMAIL = "EMAIL"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default=Channel.LOG.value, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Whether the send succeeded. Always true for a LOG row — writing it *is*
    # delivering it — and the provider's verdict for an outbound one, so a failed
    # SMS stays visible instead of vanishing into the log file.
    delivered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class NotificationPreference(Base):
    """A user's outbound channel opt-ins. One row per user, created on demand.

    Defaults mirror what a customer expects on signing up: email and push on,
    SMS off. SMS is the one channel that costs per message and reaches people
    who never asked for it, so it is opt-in rather than opt-out.
    """

    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DeviceToken(Base):
    """A push target registered by one of a user's devices.

    A user has as many as they have devices, and the same token can move between
    users (a shared phone, a reinstall), so the token is unique on its own and
    re-registering it re-points it rather than failing.
    """

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

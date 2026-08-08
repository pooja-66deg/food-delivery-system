"""Tables this service owns. Matches services/notifications/alembic/versions/0001_initial.py.

Every ``user_id`` here is a bare integer, not a foreign key. There is no users
table in this database and there must not be one: needing to check that a user
exists before recording a notification would make this service unable to work
while the users service is down, which is exactly the coupling being removed.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


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
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default=Channel.LOG.value, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # True for a LOG row — writing it is delivering it — and the provider's
    # verdict for an outbound one, so a failed SMS stays visible rather than
    # vanishing into the log file.
    delivered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class NotificationPreference(Base):
    """A user's outbound channel opt-ins. One row per user, created on demand.

    SMS is the one channel that costs per message and reaches people who never
    asked for it, so it is opt-in rather than opt-out.
    """

    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DeviceToken(Base):
    """A push target registered by one of a user's devices.

    The token is unique on its own, so re-registering one that moved between
    users (a shared phone, a reinstall) re-points it rather than failing.
    """

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Contact(Base):
    """How to reach a user. The only copy of it outside the users service.

    This is where contact details belong: the service that actually sends to
    them. Nothing else needs an address to do its job, so nothing else holds
    one — an order event carries a customer id, and this service resolves it.

    Fed by ``user-contact-events`` — the restricted topic, subscribed to only by
    services with a reason to hold an address, so the details do not reach every
    consumer of ``user-events``.
    """

    __tablename__ = "contacts"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OutboxEvent(Base):
    """This service's own outbox, for events it publishes in turn."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

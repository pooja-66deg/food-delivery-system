"""Notification model — a delivery log per architecture (log channel for MVP)."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

"""Transactional outbox model.

Domain writes append an ``OutboxEvent`` row in the SAME transaction as their
state change. A relay later publishes unpublished rows to Kafka and stamps
``published_at``. This avoids the dual-write problem (state committed but event
lost, or vice versa).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

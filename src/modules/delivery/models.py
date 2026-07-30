"""Delivery assignment model. One delivery per order; one active order per driver."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryStatus(str, Enum):
    UNASSIGNED = "UNASSIGNED"   # no driver available yet
    ASSIGNED = "ASSIGNED"       # offered to a driver, awaiting their accept
    ACCEPTED = "ACCEPTED"       # driver accepted; will pick up
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True, nullable=False)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=DeliveryStatus.UNASSIGNED.value, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

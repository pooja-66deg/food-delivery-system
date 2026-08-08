"""Tables this service owns.

``idempotency_key`` is the important one here. Once calls cross a network they
get retried — by a client, a gateway, or a Kafka consumer replaying an event —
and this column is what stops a retry becoming a second charge. It mattered in
the monolith; in the split it is load-bearing.

``OrderSnapshot`` is a read-model. Authorising a charge needs the order's total
and payment method, and asking the orders service for them would mean a customer
cannot pay whenever that service is slow. The event carries them instead.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Provider(str, Enum):
    COD = "COD"
    CARD = "CARD"


class PaymentTxStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"   # COD: to be collected; card: hold placed
    SUCCEEDED = "SUCCEEDED"     # collected / captured
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cross-service: the order lives in orders_db. Still unique — one payment
    # per order — which this service enforces alone.
    order_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PaymentTxStatus.PENDING.value, nullable=False
    )
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OrderSnapshot(Base):
    """What this service knows about an order, from the orders service's events.

    Enough to price and authorise a charge, and to answer "my payments" without
    a join across services. Everything else about the order is none of this
    service's business.
    """

    __tablename__ = "order_snapshots"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="COD", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OutboxEvent(Base):
    """This service's own outbox.

    Carries the one thing the rest of the platform waits on: that money moved.
    """

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

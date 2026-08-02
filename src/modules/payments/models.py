"""SQLAlchemy model + enums for the payments domain.

One payment record per order (MVP). Cash-on-Delivery is authorized at order
creation ("to be collected") and settled on delivery; a full refund marks the
payment REFUNDED. Online (card) payments run through the same states behind a
provider abstraction (see ``providers.py``).
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.database import Base


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
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PaymentTxStatus.PENDING.value, nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

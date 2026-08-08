"""Tables this service owns — all of them read-models.

Admin is the one service that legitimately reads across the whole platform, and
that makes it the one place the split is genuinely awkward. "Total GMV, user
count, orders by status" is a single query in a monolith and a distributed join
in a microservice architecture. There is no arrangement that makes it free.

Two ways to pay for it. Call every service on every page load — simple, and it
makes the operator console the most coupled thing on the platform, down whenever
any one service is. Or keep local copies, updated from events — which is this.

The trade is staleness: a number here may be a second or two behind. For a
reporting console that is the right trade, and it is the reason the console still
works when a service is down: it reports what it last heard, rather than failing
to report at all.

Nothing here is authoritative. Every row is a copy, and no other service reads
this database.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRow(Base):
    """A user, as the console lists them.

    Carries email and phone, because an operator looking someone up needs to
    recognise them. That is why this service subscribes to the restricted
    ``user-contact-events`` topic alongside notifications — it has a reason to
    hold an address, where orders and delivery do not.
    """

    __tablename__ = "user_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RestaurantRow(Base):
    """A restaurant, for the count and for naming one in a listing."""

    __tablename__ = "restaurant_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class OrderRow(Base):
    """An order, for the listing and for every number on the stats page.

    The status is overwritten in place rather than appended: the console reports
    where orders *are*, not how they got there, and the orders service keeps the
    transition log for anyone who needs the history.
    """

    __tablename__ = "order_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )

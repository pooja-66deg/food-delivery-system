"""Tables this service owns.

Two kinds, and the difference matters.

``Delivery`` is this service's own data — it is the only writer, and the row is
the truth about an assignment.

``OrderSnapshot`` and ``Driver`` are **read-models**: local copies of facts that
belong to other services, kept current by consuming their events. They exist
because the alternative is calling those services on every assignment, which
would make this one fail whenever they do.

A read-model is allowed to be slightly stale — a driver renamed a second ago may
show their old name — and that is the trade being made. It is never allowed to
be authoritative: this service must not decide whether an order exists, only
what it knows about one it was told about.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryStatus(str, Enum):
    UNASSIGNED = "UNASSIGNED"   # no driver available yet
    ASSIGNED = "ASSIGNED"       # offered to a driver, awaiting their accept
    ACCEPTED = "ACCEPTED"       # driver accepted; will pick up
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"


ACTIVE_STATUSES = (
    DeliveryStatus.ASSIGNED.value,
    DeliveryStatus.ACCEPTED.value,
    DeliveryStatus.PICKED_UP.value,
)


class Delivery(Base):
    """One delivery per order, one active order per driver."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    # Nullable because UNASSIGNED — no driver free yet — is a real state.
    driver_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=DeliveryStatus.UNASSIGNED.value, nullable=False
    )
    restaurant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderSnapshot(Base):
    """What this service knows about an order, from the orders service's events.

    Only the fields delivery actually uses: who to bill the journey to, and the
    two ends of it. Copying more would mean caring when more of it changes.

    The coordinates are copied rather than referenced because a driver needs to
    navigate while the restaurants and users services may be down — and a
    delivery that cannot be navigated is a delivery that did not happen.
    """

    __tablename__ = "order_snapshots"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Which kitchen, so an owner action can be checked against the roster above.
    restaurant_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    restaurant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    restaurant_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    restaurant_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Driver(Base):
    """A driver, as far as delivery needs to know: an id and a name to show.

    Populated from the users service's events. Note what is *not* here — no
    email, no password, no address. A read-model copies what its owner uses, not
    what the source happens to have, or every service ends up holding personal
    data it has no reason to.
    """

    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    # A deactivated driver stops being offered work but keeps their history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RestaurantSnapshot(Base):
    """Who owns a restaurant, from the restaurants service's events.

    Copied for exactly one question: may this caller reassign the driver on this
    order? ``require_role("restaurant", "admin")`` on the route says the caller
    is *a* restaurant, not that they own *this* one — and without the difference
    any restaurant account could reassign the driver on any order on the
    platform.

    Answering it needs an owner id, which is the restaurants service's fact.
    Asking that service per reassignment would make an owner action fail whenever
    it is slow; one integer copied by event does not.
    """

    __tablename__ = "restaurant_snapshots"

    restaurant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OutboxEvent(Base):
    """This service's own outbox, for the events it publishes in turn."""

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

"""Tables this service owns. Matches services/users/alembic/versions/0001_initial.py.

This is the one service with no read-models: it is the source of identity, so it
copies nothing from anywhere. Everything else keeps a copy of *its* data, which
is why the events it publishes matter more than the ones it consumes — it
consumes none.

``favorites.restaurant_id`` is a plain integer. Restaurants live in another
database, so whether one exists is not a question this service can answer, and
the unique constraint carries the correctness that matters: favouriting twice
does not create two rows.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A platform user (customer, restaurant, driver, or admin)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_reset_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Where a restaurant applicant stands with the operator, mirrored from the
    #: restaurants service by the consumer. NULL for every other role — a
    #: customer has no application, and "approved" there would describe a
    #: decision nobody made.
    #:
    #: This service does not decide it and must not: the restaurants service owns
    #: approval. What is held here is only what login needs to say something true
    #: to somebody it is turning away, because "inactive" alone cannot tell
    #: "waiting" from "rejected" from "switched off last year".
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Bumped to evict every existing session (an authenticated password change is
    # now the only thing that does so). Tokens carry the value they were minted
    # with as a "gen" claim.
    #
    # Worth knowing in the split: other services verify tokens locally and do
    # not see this column, so a bump reaches them only when the access token
    # expires. That window is the access token's lifetime, and it is the price
    # of not making this service a synchronous dependency of every request.
    session_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Address(Base):
    """A delivery address owned by a user."""

    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Same database, so this one stays a real foreign key.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(50), default="home", nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="addresses")


class Favorite(Base):
    """One row per (user, restaurant) pair.

    The unique constraint is the whole correctness story: favouriting twice must
    not create a duplicate, and enforcing that in the database rather than by
    checking first means two concurrent taps cannot both slip through.
    """

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "restaurant_id", name="uq_favorite_user_restaurant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # Cross-service: restaurants live in restaurants_db.
    restaurant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class OutboxEvent(Base):
    """This service's own outbox.

    Busier here than elsewhere: users is the service everyone keeps a copy of,
    so almost every write publishes something.
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

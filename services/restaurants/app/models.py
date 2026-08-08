"""Tables this service owns.

The catalogue — venues, menus, stock — plus reviews, which live here because the
read that matters is "this restaurant's rating" and it happens on every listing.
Beside the restaurant, that read stays inside one service.

``OrderSnapshot`` is a read-model, and it exists for exactly one job: deciding
whether someone may review. The rule is "you may review an order you placed and
that was delivered", and both of those are the orders service's facts. Asking it
per review would make writing one fail whenever it is down; copying the two
fields it takes to answer does not.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cross-service: the owner is a user, in users_db. Ownership is checked
    # against the caller's token, which already carries their id — so this
    # service never needs to ask who they are.
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0"), nullable=False
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # NULL means "not set" and falls back to the platform default, not to
    # unlimited — see zones.effective_radius_km.
    delivery_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), index=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("menu_categories.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # The owner's manual switch. Never rewritten by the system, so "turned off"
    # stays distinguishable from "sold out".
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # NULL means stock is not tracked for this item.
    stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Not nullable: "unknown" and "not vegetarian" must give the same answer, or
    # a diner filtering for vegetarian food gets shown an unlabelled dish.
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Review(Base):
    """A customer's rating of a completed order."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cross-service: the order lives in orders_db. Still unique — one review per
    # order — which this service enforces alone.
    order_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), index=True, nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    # The reviewer's public name, copied at write time rather than joined.
    # There is no users table in this database, and keeping a full copy of every
    # user just to render "Alex R." would spread personal data across a service
    # that has no other use for it. Copying the display string is the smallest
    # thing that answers the question — and it is also what should be shown: the
    # name they reviewed under, like order_items keeps the price paid.
    reviewer_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # The owner's public response. Null until they answer; editing overwrites
    # rather than threading, because a review is a one-exchange affair and a
    # thread invites an argument.
    owner_reply: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner_replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Set only when the author edits. Null means "never edited" — not "edited at
    # creation time", which is what defaulting to now() would imply.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderSnapshot(Base):
    """What this service knows about an order, from the orders service's events.

    Three fields, because three is all the review rule needs: whose order it
    was, which restaurant it was for, and whether it reached DELIVERED. Copying
    more would mean caring when more of it changes.
    """

    __tablename__ = "order_snapshots"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    #: Display name, so a review can carry it without a users table here.
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    restaurant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
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

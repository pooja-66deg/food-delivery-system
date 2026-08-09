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


# The approval states a restaurant moves through, and the food types an owner
# may declare. Defined here, beside the columns they constrain, so service.py
# and discovery.py can each import them without importing each other.
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
APPROVAL_STATUSES = (PENDING, APPROVED, REJECTED)

FOOD_TYPES = ("veg", "non_veg", "both")


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
    # Whether an operator has let this venue onto the platform. Owners register
    # themselves, so "exists" and "may trade" stopped being the same thing —
    # everything customer-facing filters on this, and only an admin may change
    # it. Indexed because browse now carries the predicate on every request.
    #
    # Deliberately a plain string, not a native PG enum: adding a state to an
    # enum needs its own migration and a table rewrite, and this is exactly the
    # kind of column that grows a "suspended" later.
    approval_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True, nullable=False
    )
    #: Why an admin rejected it. Shown to the owner — a rejection they cannot
    #: see the reason for is one they cannot act on.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What the kitchen serves: "veg", "non_veg" or "both". The owner's own
    # declaration about the venue, which is why the customer Vegetarian filter
    # reads it rather than inferring from the menu — a restaurant with one
    # vegetarian side dish is not a vegetarian restaurant.
    food_type: Mapped[str] = mapped_column(
        String(10), default="both", index=True, nullable=False
    )
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


class OwnerRow(Base):
    """A restaurant owner's name, copied from ``user-events``.

    Read-model, like ``OrderSnapshot`` beside it. The admin restaurant list has
    to show who owns each venue, and owners are rows in another service's
    database — so the choice is a synchronous call to users on every page load,
    or a local copy. The same reasoning that produced the delivery service's
    driver roster produces this.

    A name only. This service has no reason to hold an owner's email or phone,
    so it does not subscribe to ``user-contact-events`` where those travel — the
    restaurant's *own* phone number is a column on Restaurant and is what a
    listing shows anyway.

    Missing rows are normal and must stay survivable: an owner who registered
    before this table existed has no event to replay, and the list renders them
    as an unknown name rather than failing.
    """

    __tablename__ = "owner_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


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

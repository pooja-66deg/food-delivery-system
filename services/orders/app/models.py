"""Tables this service owns.

The order, its lines, and the transition log behind them.

Note what ``OrderItem`` already did in the monolith: it stores the dish's
``name`` and ``unit_price`` rather than pointing at a menu row. That was right
then — a receipt must not change when a restaurant edits its menu — and it is
exactly what the split needs everywhere, because there is no menu table in this
database to join to.

``AddressSnapshot`` is a read-model. Checkout has to know where an order is
going, and asking the users service on every checkout would make placing an
order fail whenever that service is slow. It carries city and coordinates only —
never the street line, which this service has no use for.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """This service's declarative base — not the monolith's."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    RESTAURANT_ACCEPTED = "RESTAURANT_ACCEPTED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PaymentMethod(str, Enum):
    COD = "COD"
    CARD = "CARD"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class RefundStatus(str, Enum):
    NONE = "NONE"
    FULL = "FULL"
    PARTIAL = "PARTIAL"


class Actor(str, Enum):
    CUSTOMER = "CUSTOMER"
    RESTAURANT = "RESTAURANT"
    DRIVER = "DRIVER"
    SYSTEM = "SYSTEM"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    # All three are cross-service: users_db, restaurants_db, users_db.
    customer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    address_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default=OrderStatus.CREATED.value, nullable=False
    )
    payment_method: Mapped[str] = mapped_column(
        String(20), default=PaymentMethod.COD.value, nullable=False
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), default=PaymentStatus.PENDING.value, nullable=False
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0"), nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refund_status: Mapped[str] = mapped_column(
        String(20), default=RefundStatus.NONE.value, nullable=False
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0"), nullable=False
    )
    cancelled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    events: Mapped[list["OrderStatusEvent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusEvent.id"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    # Cross-service, and already a plain integer in the monolith: the line
    # carries its own name and price, so the menu row is a back-reference rather
    # than something to join to.
    menu_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    order: Mapped["Order"] = relationship(back_populates="events")


class AddressSnapshot(Base):
    """Where an order can be delivered, from the users service's events.

    City and coordinates, nothing else. Checkout needs to ask the restaurants
    service "do you deliver here?", and that question takes a point and a city —
    not a street line this service would then be storing for no reason.
    """

    __tablename__ = "address_snapshots"

    address_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CustomerSnapshot(Base):
    """Who to reach about an order, from the users service's events.

    A display name and nothing else. The restaurants service puts it on a review
    byline, and orders is the service that publishes the event carrying it.

    Deliberately no email or phone: an address belongs in the service that sends
    to it, which is notifications, and it gets its own from a topic only it
    subscribes to. Copying contact details here would mean a second database
    holding them for no reason — this service never contacts anyone.
    """

    __tablename__ = "customer_snapshots"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RestaurantSnapshot(Base):
    """Who owns a restaurant, and what it is called.

    Two questions orders cannot answer alone: "may this caller accept this
    order?" (the owner check every restaurant action needs) and "which kitchen
    is this ticket for?" (the dashboard mixes several).

    Both used to be a join. Calling the restaurants service for them would put a
    second synchronous dependency on the busiest path in the owner dashboard, so
    they arrive by event instead — and checkout keeps its single sync call.
    """

    __tablename__ = "restaurant_snapshots"

    restaurant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OutboxEvent(Base):
    """This service's own outbox.

    The busiest on the platform: an order status change is what payments,
    delivery, restaurants and notifications all react to.
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

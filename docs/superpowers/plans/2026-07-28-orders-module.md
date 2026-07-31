# Orders Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dead-end `/cart/checkout` into a persisted order with a validated state machine, COD cancellation/refund rules, restaurant accept/reject + timeout logic, and Alembic migrations.

**Architecture:** New `src/modules/orders/` domain module (models, enums, state machine, schemas, service, router) following the existing modular-monolith patterns. Orders are persisted in PostgreSQL; status changes go through one central `apply_transition` that validates against an allowed-transitions map and writes an append-only `OrderStatusEvent`. Checkout reuses the existing 5-gate `validate_checkout` validator, then persists its `ValidatedOrder`. Alembic replaces `Base.metadata.create_all` for production schema management (tests keep `create_all`).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async (asyncpg), Pydantic v2, Redis (async), Alembic, pytest + pytest-asyncio + aiosqlite + fakeredis.

## Global Constraints

- Python ≥ 3.11; SQLAlchemy 2.0 `Mapped`/`mapped_column` style (match `restaurants/models.py`).
- Money is always `Numeric(10, 2)` / `Decimal`.
- Timezone-aware datetimes via a module-level `_utcnow()` (match existing models). Any time-dependent *logic* (the acceptance timeout) takes `now` as an injected parameter so it is deterministically testable.
- Enums are stored as `String` columns holding a `str`-valued `Enum`'s value (match how `User.role` is a plain string); compare with enum members directly (`order.status == OrderStatus.CREATED` works because members subclass `str`).
- All new endpoints reuse existing auth deps: `get_current_user`, `require_role("restaurant", "admin")`, and `restaurants.service.owned_restaurant`.
- Reuse existing exceptions (`NotFoundException`, `ForbiddenException`, `ConflictException`). Machine-readable client errors use an `OrderError(AppException)` carrying `details={"code": ...}` (mirrors `cart.checkout.CheckoutError`).
- Tests run on in-memory SQLite + fakeredis via the existing `tests/conftest.py` fixtures (`api_client`, `db_session`, `fake_redis`). No live infra.
- Run the full suite with env vars set: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret`.
- Delivery fee is `Decimal("0")` for MVP; `total == subtotal`.

---

### Task 1: Orders enums + models

**Files:**
- Create: `src/modules/orders/models.py`
- Modify: `tests/conftest.py` (register the new model module on `Base.metadata`)
- Modify: `src/main.py` (import the model module so `create_all`/metadata sees it — line ~20, next to the other model imports)
- Test: `tests/modules/orders/test_models.py`
- Create: `tests/modules/orders/__init__.py` (empty)

**Interfaces:**
- Produces (enums, all `str`-valued): `OrderStatus` (`CREATED, PAYMENT_PENDING, PAYMENT_SUCCESS, RESTAURANT_ACCEPTED, PREPARING, READY_FOR_PICKUP, OUT_FOR_DELIVERY, DELIVERED, COMPLETED, CANCELLED, REJECTED`), `PaymentMethod` (`COD`), `PaymentStatus` (`PENDING, SUCCESS, FAILED, REFUNDED`), `RefundStatus` (`NONE, FULL, PARTIAL`), `Actor` (`CUSTOMER, RESTAURANT, SYSTEM`).
- Produces (models): `Order`, `OrderItem`, `OrderStatusEvent` with the columns below. `Order.items` and `Order.events` are `relationship(cascade="all, delete-orphan")`.

- [ ] **Step 1: Create the empty test package**

Create `tests/modules/orders/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

```python
# tests/modules/orders/test_models.py
"""Model-layer tests for the orders domain."""
from decimal import Decimal

import pytest

from src.modules.orders.models import (
    Order, OrderItem, OrderStatusEvent,
    OrderStatus, PaymentMethod, PaymentStatus, RefundStatus, Actor,
)


@pytest.mark.asyncio
async def test_order_persists_with_items_and_event(db_session):
    order = Order(
        customer_id=1, restaurant_id=1, address_id=1,
        status=OrderStatus.CREATED, payment_method=PaymentMethod.COD,
        payment_status=PaymentStatus.PENDING, subtotal=Decimal("20.00"),
        delivery_fee=Decimal("0"), total=Decimal("20.00"),
        refund_status=RefundStatus.NONE, refund_amount=Decimal("0"),
    )
    order.items.append(
        OrderItem(menu_item_id=5, name="Pizza", unit_price=Decimal("10.00"),
                  quantity=2, line_total=Decimal("20.00"))
    )
    order.events.append(
        OrderStatusEvent(from_status=None, to_status=OrderStatus.CREATED, actor=Actor.SYSTEM)
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    assert order.id is not None
    assert order.status == OrderStatus.CREATED           # str-enum compares to stored value
    assert order.items[0].line_total == Decimal("20.00")
    assert order.events[0].to_status == OrderStatus.CREATED
```

- [ ] **Step 3: Run test to verify it fails**

Run: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret .venv/Scripts/python -m pytest tests/modules/orders/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: src.modules.orders.models`.

- [ ] **Step 4: Write the implementation**

```python
# src/modules/orders/models.py
"""SQLAlchemy models + enums for the orders domain."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


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
    SYSTEM = "SYSTEM"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), index=True, nullable=False)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.CREATED.value, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default=PaymentMethod.COD.value, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING.value, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refund_status: Mapped[str] = mapped_column(String(20), default=RefundStatus.NONE.value, nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    cancelled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
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
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="events")
```

- [ ] **Step 5: Register the model module for metadata**

In `tests/conftest.py`, after the existing model imports (around line 21), add:

```python
import src.modules.orders.models  # noqa: F401,E402
```

In `src/main.py`, after the existing `import src.modules.restaurants.models` line (~20), add:

```python
import src.modules.orders.models  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

Run: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret .venv/Scripts/python -m pytest tests/modules/orders/test_models.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/modules/orders/models.py tests/modules/orders/ src/main.py tests/conftest.py
git commit -m "feat(orders): add order models and enums"
```

---

### Task 2: Order state machine (transitions + refund rules)

**Files:**
- Create: `src/modules/orders/state_machine.py`
- Test: `tests/modules/orders/test_state_machine.py`

**Interfaces:**
- Consumes: `OrderStatus`, `Actor`, `RefundStatus`, `Order`, `OrderStatusEvent` from `orders.models`.
- Produces:
  - `ALLOWED: dict[OrderStatus, set[OrderStatus]]`
  - `PRE_PREP_STATES: set[OrderStatus]` = `{CREATED, PAYMENT_PENDING, PAYMENT_SUCCESS, RESTAURANT_ACCEPTED}`
  - `class OrderError(AppException)` with `__init__(self, code: str, message: str)` → `status_code=409`, `details={"code": code}`.
  - `assert_transition_allowed(current: OrderStatus, to: OrderStatus) -> None` — raises `OrderError("ILLEGAL_TRANSITION", ...)` if `to not in ALLOWED[current]`.
  - `apply_transition(session, order: Order, to: OrderStatus, actor: Actor, reason: str | None = None) -> None` — validates, sets `order.status = to.value`, appends an `OrderStatusEvent` (does NOT commit; caller commits). Requires `order.id` to be set (order flushed).
  - `customer_cancel_allowed(current: OrderStatus) -> bool` = `current in PRE_PREP_STATES`.
  - `refund_on_cancel(current: OrderStatus, actor: Actor) -> RefundStatus` — `SYSTEM`→FULL; `CUSTOMER`→FULL (only reachable pre-prep); `RESTAURANT`→FULL if pre-prep else NONE.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/orders/test_state_machine.py
import pytest

from src.modules.orders.models import Actor, OrderStatus, RefundStatus
from src.modules.orders import state_machine as sm


def test_legal_transition_passes():
    sm.assert_transition_allowed(OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING)  # no raise


def test_skipping_transition_rejected():
    with pytest.raises(sm.OrderError) as exc:
        sm.assert_transition_allowed(OrderStatus.CREATED, OrderStatus.OUT_FOR_DELIVERY)
    assert exc.value.details["code"] == "ILLEGAL_TRANSITION"


def test_terminal_states_reject_all():
    for terminal in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
        with pytest.raises(sm.OrderError):
            sm.assert_transition_allowed(terminal, OrderStatus.PREPARING)


@pytest.mark.parametrize("status,expected", [
    (OrderStatus.CREATED, True), (OrderStatus.RESTAURANT_ACCEPTED, True),
    (OrderStatus.PREPARING, False), (OrderStatus.OUT_FOR_DELIVERY, False),
])
def test_customer_cancel_window(status, expected):
    assert sm.customer_cancel_allowed(status) is expected


@pytest.mark.parametrize("status,actor,expected", [
    (OrderStatus.PAYMENT_SUCCESS, Actor.CUSTOMER, RefundStatus.FULL),
    (OrderStatus.PREPARING, Actor.RESTAURANT, RefundStatus.NONE),
    (OrderStatus.PAYMENT_SUCCESS, Actor.RESTAURANT, RefundStatus.FULL),
    (OrderStatus.PREPARING, Actor.SYSTEM, RefundStatus.FULL),
])
def test_refund_matrix(status, actor, expected):
    assert sm.refund_on_cancel(status, actor) is expected
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_state_machine.py -v` (env prefix as in Task 1).
Expected: FAIL — `ModuleNotFoundError: src.modules.orders.state_machine`.

- [ ] **Step 3: Write the implementation**

```python
# src/modules/orders/state_machine.py
"""Central order state machine: legal transitions + COD refund rules."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppException
from src.modules.orders.models import Actor, Order, OrderStatus, OrderStatusEvent, RefundStatus

S = OrderStatus

ALLOWED: dict[OrderStatus, set[OrderStatus]] = {
    S.CREATED: {S.PAYMENT_PENDING, S.CANCELLED},
    S.PAYMENT_PENDING: {S.PAYMENT_SUCCESS, S.CANCELLED},
    S.PAYMENT_SUCCESS: {S.RESTAURANT_ACCEPTED, S.CANCELLED, S.REJECTED},
    S.RESTAURANT_ACCEPTED: {S.PREPARING, S.CANCELLED},
    S.PREPARING: {S.READY_FOR_PICKUP, S.CANCELLED},
    S.READY_FOR_PICKUP: {S.OUT_FOR_DELIVERY, S.CANCELLED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED, S.CANCELLED},
    S.DELIVERED: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
    S.REJECTED: set(),
}

PRE_PREP_STATES: set[OrderStatus] = {
    S.CREATED, S.PAYMENT_PENDING, S.PAYMENT_SUCCESS, S.RESTAURANT_ACCEPTED,
}


class OrderError(AppException):
    """A client-actionable order error; ``code`` is a stable machine reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message, status_code=409, details={"code": code})
        self.code = code


def assert_transition_allowed(current: OrderStatus, to: OrderStatus) -> None:
    if to not in ALLOWED[OrderStatus(current)]:
        raise OrderError(
            "ILLEGAL_TRANSITION",
            f"Cannot move order from {OrderStatus(current).value} to {OrderStatus(to).value}.",
        )


def apply_transition(
    session: AsyncSession, order: Order, to: OrderStatus, actor: Actor, reason: str | None = None
) -> None:
    """Validate + apply a status change and append an audit event. No commit."""
    assert_transition_allowed(OrderStatus(order.status), to)
    session.add(
        OrderStatusEvent(
            order_id=order.id, from_status=order.status, to_status=to.value,
            actor=actor.value, reason=reason,
        )
    )
    order.status = to.value


def customer_cancel_allowed(current: OrderStatus) -> bool:
    return OrderStatus(current) in PRE_PREP_STATES


def refund_on_cancel(current: OrderStatus, actor: Actor) -> RefundStatus:
    if actor == Actor.SYSTEM:
        return RefundStatus.FULL
    if actor == Actor.CUSTOMER:
        return RefundStatus.FULL  # only reachable from pre-prep states
    # RESTAURANT approval
    return RefundStatus.FULL if OrderStatus(current) in PRE_PREP_STATES else RefundStatus.NONE
```

- [ ] **Step 4: Run to verify pass**

Run: `... -m pytest tests/modules/orders/test_state_machine.py -v`
Expected: PASS (all params).

- [ ] **Step 5: Commit**

```bash
git add src/modules/orders/state_machine.py tests/modules/orders/test_state_machine.py
git commit -m "feat(orders): state machine transitions and refund rules"
```

---

### Task 3: Order schemas + creation service (checkout → persisted order)

**Files:**
- Create: `src/modules/orders/schemas.py`
- Create: `src/modules/orders/service.py`
- Test: `tests/modules/orders/test_service_create.py`

**Interfaces:**
- Consumes: `cart.checkout.validate_checkout(redis, session, user, request) -> ValidatedOrder`; `cart.service.clear_cart(redis, user_id)`; `cart.schemas.CheckoutRequest`; `apply_transition`; models + enums; `OrderError`.
- Produces (schemas): `OrderItemRead`, `OrderStatusEventRead`, `OrderRead` (all `model_config = ConfigDict(from_attributes=True)`), `OrderSummary`.
- Produces (service): `async def create_order_from_checkout(redis, session, user, request: CheckoutRequest) -> Order`. Acquires a Redis `SET NX` lock `order_lock:{user_id}` (TTL 10s); raises `OrderError("CHECKOUT_IN_PROGRESS", ...)` if not acquired; validates via `validate_checkout`; builds `Order` (COD, delivery_fee=0, total=subtotal) + `OrderItem`s; flushes; auto-advances `CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS` (actor SYSTEM), setting `payment_status=SUCCESS`; commits; clears cart; releases lock in `finally`; returns the `Order` with items+events loaded.

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/orders/test_service_create.py
from decimal import Decimal

import pytest

from src.modules.orders.models import OrderStatus, PaymentStatus


async def _seed_ready_cart(api_client):
    # owner + restaurant + item
    await api_client.post("/auth/register", json={"email": "o@x.com", "phone": "+15559100001",
        "first_name": "O", "last_name": "W", "password": "supersecret1", "role": "restaurant"})
    owner = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "o@x.com", "password": "supersecret1"})).json()["access_token"]}
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    # customer + cart + address
    await api_client.post("/auth/register", json={"email": "c@x.com", "phone": "+15559100002",
        "first_name": "C", "last_name": "U", "password": "supersecret1", "role": "customer"})
    cust = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "c@x.com", "password": "supersecret1"})).json()["access_token"]}
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return cust, addr, price_hash


@pytest.mark.asyncio
async def test_create_order_from_checkout_persists_everything(api_client, fake_redis, db_session):
    # Exercise the service directly through the router added in Task 7, so this
    # test is written now but asserts the end state the service must produce.
    cust, addr, price_hash = await _seed_ready_cart(api_client)
    resp = await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": price_hash}, headers=cust)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == OrderStatus.PAYMENT_SUCCESS.value
    assert body["payment_status"] == PaymentStatus.SUCCESS.value
    assert body["total"] == "20.00"
    assert len(body["items"]) == 1 and body["items"][0]["quantity"] == 2
    # three status events: CREATED, PAYMENT_PENDING, PAYMENT_SUCCESS
    assert [e["to_status"] for e in body["events"]] == [
        OrderStatus.CREATED.value, OrderStatus.PAYMENT_PENDING.value, OrderStatus.PAYMENT_SUCCESS.value]
    # cart cleared
    assert (await api_client.get("/cart", headers=cust)).json()["items"] == []
```

> This test depends on the `/orders/checkout` route from Task 7. Expected to fail until then. Implement the service now; it will be wired in Task 7. Run it after Task 7. For an isolated Task-3 check, also add the direct-service test below.

```python
# append to tests/modules/orders/test_service_create.py
@pytest.mark.asyncio
async def test_double_submit_lock(fake_redis, db_session):
    from src.modules.orders import service
    await fake_redis.set("order_lock:1", "1")  # simulate in-flight checkout
    from src.modules.orders.state_machine import OrderError
    from src.modules.cart.schemas import CheckoutRequest

    class _U:  # minimal stand-in for User
        id = 1
    with pytest.raises(OrderError) as exc:
        await service.create_order_from_checkout(
            fake_redis, db_session, _U(), CheckoutRequest(address_id=1, price_hash="x"))
    assert exc.value.details["code"] == "CHECKOUT_IN_PROGRESS"
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_service_create.py::test_double_submit_lock -v`
Expected: FAIL — `ModuleNotFoundError: src.modules.orders.service`.

- [ ] **Step 3: Write schemas**

```python
# src/modules/orders/schemas.py
"""Read/response schemas for the orders domain."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    menu_item_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    actor: str
    reason: str | None
    at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    restaurant_id: int
    address_id: int
    status: str
    payment_method: str
    payment_status: str
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    refund_status: str
    refund_amount: Decimal
    cancelled_by: str | None
    cancel_reason: str | None
    created_at: datetime
    items: list[OrderItemRead]
    events: list[OrderStatusEventRead]


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    restaurant_id: int
    status: str
    total: Decimal
    created_at: datetime
```

- [ ] **Step 4: Write the creation service**

```python
# src/modules/orders/service.py
"""Order lifecycle service."""
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.cart import checkout as checkout_service
from src.modules.cart import service as cart_service
from src.modules.cart.schemas import CheckoutRequest
from src.modules.orders import state_machine as sm
from src.modules.orders.models import (
    Actor, Order, OrderItem, OrderStatus, PaymentMethod, PaymentStatus,
)
from src.modules.orders.state_machine import OrderError

_LOCK_KEY = "order_lock:{user_id}"
_LOCK_TTL = 10


async def _load_full(session: AsyncSession, order_id: int) -> Order:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.events))
    )
    return (await session.scalars(stmt)).one()


async def create_order_from_checkout(
    redis: Redis, session: AsyncSession, user, request: CheckoutRequest
) -> Order:
    lock_key = _LOCK_KEY.format(user_id=user.id)
    acquired = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL)
    if not acquired:
        raise OrderError("CHECKOUT_IN_PROGRESS", "A checkout is already in progress.")
    try:
        validated = await checkout_service.validate_checkout(redis, session, user, request)

        order = Order(
            customer_id=user.id,
            restaurant_id=validated.restaurant_id,
            address_id=validated.address_id,
            status=OrderStatus.CREATED.value,
            payment_method=PaymentMethod.COD.value,
            payment_status=PaymentStatus.PENDING.value,
            subtotal=validated.subtotal,
            delivery_fee=Decimal("0"),
            total=validated.subtotal,
        )
        for it in validated.items:
            order.items.append(
                OrderItem(menu_item_id=it.menu_item_id, name=it.name,
                          unit_price=it.unit_price, quantity=it.quantity, line_total=it.line_total)
            )
        session.add(order)
        await session.flush()  # assign order.id before writing events

        # Record the CREATED baseline event, then advance COD to PAYMENT_SUCCESS.
        session.add(
            sm.OrderStatusEvent(order_id=order.id, from_status=None,
                                to_status=OrderStatus.CREATED.value, actor=Actor.SYSTEM.value)
        )
        sm.apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
        sm.apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM,
                            reason="COD: to be collected on delivery")
        order.payment_status = PaymentStatus.SUCCESS.value

        await session.commit()
        await cart_service.clear_cart(redis, user.id)
        return await _load_full(session, order.id)
    finally:
        await redis.delete(lock_key)
```

> Note: `sm.OrderStatusEvent` is re-exported implicitly because `state_machine` imports it; if the linter objects, import `OrderStatusEvent` directly from `orders.models` in `service.py` instead. Prefer the direct import: add `OrderStatusEvent` to the models import line and use it.

- [ ] **Step 5: Run the isolated service test**

Run: `... -m pytest tests/modules/orders/test_service_create.py::test_double_submit_lock -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/modules/orders/schemas.py src/modules/orders/service.py tests/modules/orders/test_service_create.py
git commit -m "feat(orders): schemas and checkout-to-order creation service"
```

---

### Task 4: Order query service (history + detail with ownership)

**Files:**
- Modify: `src/modules/orders/service.py`
- Test: `tests/modules/orders/test_service_query.py`

**Interfaces:**
- Produces:
  - `async def list_orders(session, customer_id: int, limit: int = 20, offset: int = 0) -> list[Order]` — caller's orders, newest first (`order_by(Order.created_at.desc(), Order.id.desc())`).
  - `async def get_order_for_user(session, user, order_id: int) -> Order` — loads full order; `NotFoundException` if missing; visible if `user.id == order.customer_id`, or the user owns the restaurant (`restaurants.service.owned_restaurant` succeeds), or `user.role == "admin"`; else `ForbiddenException`.

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/orders/test_service_query.py
import pytest

from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.orders import service
from src.modules.orders.models import Order, OrderStatus
from src.modules.users.models import User
from decimal import Decimal


async def _make_order(session, customer_id=1, restaurant_id=1):
    order = Order(customer_id=customer_id, restaurant_id=restaurant_id, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("5"), total=Decimal("5"))
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_list_orders_newest_first(db_session):
    await _make_order(db_session)
    await _make_order(db_session)
    orders = await service.list_orders(db_session, customer_id=1)
    assert len(orders) == 2 and orders[0].id > orders[1].id


@pytest.mark.asyncio
async def test_get_order_forbidden_for_other_customer(db_session):
    order = await _make_order(db_session, customer_id=1)
    other = User(id=99, email="x@y.com", phone="+1", first_name="a", last_name="b",
                 hashed_password="h", role="customer")
    db_session.add(other)
    await db_session.commit()
    with pytest.raises(ForbiddenException):
        await service.get_order_for_user(db_session, other, order.id)


@pytest.mark.asyncio
async def test_get_missing_order_404(db_session):
    user = User(id=1, email="a@b.com", phone="+2", first_name="a", last_name="b",
                hashed_password="h", role="customer")
    db_session.add(user)
    await db_session.commit()
    with pytest.raises(NotFoundException):
        await service.get_order_for_user(db_session, user, 4242)
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_service_query.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'list_orders'`.

- [ ] **Step 3: Implement (append to `service.py`)**

```python
# add imports at top of service.py
from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.restaurants import service as restaurant_service
from src.core.exceptions import AppException


async def list_orders(session: AsyncSession, customer_id: int, limit: int = 20, offset: int = 0):
    stmt = (
        select(Order)
        .where(Order.customer_id == customer_id)
        .options(selectinload(Order.items), selectinload(Order.events))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit).offset(offset)
    )
    return list(await session.scalars(stmt))


async def get_order_for_user(session: AsyncSession, user, order_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    if user.id == order.customer_id or user.role == "admin":
        return await _load_full(session, order_id)
    try:
        await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    except AppException:
        raise ForbiddenException("You cannot view this order")
    return await _load_full(session, order_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `... -m pytest tests/modules/orders/test_service_query.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/modules/orders/service.py tests/modules/orders/test_service_query.py
git commit -m "feat(orders): order history and detail queries with ownership"
```

---

### Task 5: Lifecycle service (cancel / accept / reject / advance status)

**Files:**
- Modify: `src/modules/orders/service.py`
- Test: `tests/modules/orders/test_service_lifecycle.py`

**Interfaces:**
- Produces (all commit and return the reloaded full `Order`):
  - `async def cancel_by_customer(session, user, order_id) -> Order` — loads via `get_order_for_user`; if `not customer_cancel_allowed(status)` raise `OrderError("CANCEL_NOT_ALLOWED", ...)`; else `apply_transition(..., CANCELLED, CUSTOMER)`, set `cancelled_by=CUSTOMER`, `refund_status=refund_on_cancel(...)`, `refund_amount=total if FULL else 0`, `payment_status=REFUNDED if FULL`.
  - `async def accept_by_restaurant(session, user, order_id) -> Order` — `owned_restaurant` guard on `order.restaurant_id`; `apply_transition(..., RESTAURANT_ACCEPTED, RESTAURANT)`.
  - `async def reject_by_restaurant(session, user, order_id, reason=None) -> Order` — `owned_restaurant` guard; `apply_transition(..., REJECTED, RESTAURANT, reason)`, `cancelled_by=RESTAURANT`, full refund.
  - `async def advance_status(session, user, order_id, to: OrderStatus) -> Order` — `owned_restaurant` guard; `apply_transition(..., to, RESTAURANT)`; if `to == CANCELLED` apply the restaurant-cancel refund rule.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/orders/test_service_lifecycle.py
from decimal import Decimal

import pytest

from src.modules.orders import service
from src.modules.orders.models import Actor, Order, OrderStatus, RefundStatus
from src.modules.orders.state_machine import OrderError, apply_transition
from src.modules.users.models import User
from src.modules.restaurants.models import Restaurant


async def _order_in(session, status: OrderStatus, customer_id=1, owner_id=2, restaurant_id=1):
    session.add(User(id=customer_id, email=f"c{customer_id}@x.com", phone=f"+{customer_id}",
                     first_name="c", last_name="u", hashed_password="h", role="customer"))
    session.add(User(id=owner_id, email=f"o{owner_id}@x.com", phone=f"+{owner_id}0",
                     first_name="o", last_name="w", hashed_password="h", role="restaurant"))
    session.add(Restaurant(id=restaurant_id, owner_id=owner_id, name="R", city="C",
                           address_line="1", phone="+1"))
    order = Order(customer_id=customer_id, restaurant_id=restaurant_id, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("20"), total=Decimal("20"))
    session.add(order)
    await session.flush()
    # walk to the requested status through SYSTEM transitions
    path = [OrderStatus.PAYMENT_PENDING, OrderStatus.PAYMENT_SUCCESS, OrderStatus.RESTAURANT_ACCEPTED,
            OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP, OrderStatus.OUT_FOR_DELIVERY]
    for step in path:
        if OrderStatus(order.status) == status:
            break
        apply_transition(session, order, step, Actor.SYSTEM)
    await session.commit()
    return order


@pytest.mark.asyncio
async def test_customer_cancel_preprep_full_refund(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    user = await db_session.get(User, 1)
    result = await service.cancel_by_customer(db_session, user, order.id)
    assert result.status == OrderStatus.CANCELLED
    assert result.refund_status == RefundStatus.FULL
    assert result.refund_amount == Decimal("20")


@pytest.mark.asyncio
async def test_customer_cancel_after_prep_rejected(db_session):
    order = await _order_in(db_session, OrderStatus.PREPARING)
    user = await db_session.get(User, 1)
    with pytest.raises(OrderError) as exc:
        await service.cancel_by_customer(db_session, user, order.id)
    assert exc.value.details["code"] == "CANCEL_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_restaurant_accept(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    owner = await db_session.get(User, 2)
    result = await service.accept_by_restaurant(db_session, owner, order.id)
    assert result.status == OrderStatus.RESTAURANT_ACCEPTED


@pytest.mark.asyncio
async def test_restaurant_reject_full_refund(db_session):
    order = await _order_in(db_session, OrderStatus.PAYMENT_SUCCESS)
    owner = await db_session.get(User, 2)
    result = await service.reject_by_restaurant(db_session, owner, order.id, reason="86 the kitchen")
    assert result.status == OrderStatus.REJECTED
    assert result.refund_status == RefundStatus.FULL
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_service_lifecycle.py -v`
Expected: FAIL — `AttributeError: ... 'cancel_by_customer'`.

- [ ] **Step 3: Implement (append to `service.py`)**

```python
from src.modules.orders.models import RefundStatus, PaymentStatus  # extend existing import line


def _record_refund(order: Order, refund: RefundStatus) -> None:
    order.refund_status = refund.value
    if refund == RefundStatus.FULL:
        order.refund_amount = order.total
        order.payment_status = PaymentStatus.REFUNDED.value
    else:
        order.refund_amount = Decimal("0")


async def cancel_by_customer(session: AsyncSession, user, order_id: int) -> Order:
    order = await get_order_for_user(session, user, order_id)
    current = OrderStatus(order.status)
    if not sm.customer_cancel_allowed(current):
        raise OrderError("CANCEL_NOT_ALLOWED",
                         "This order can no longer be cancelled without restaurant approval.")
    sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.CUSTOMER)
    order.cancelled_by = Actor.CUSTOMER.value
    _record_refund(order, sm.refund_on_cancel(current, Actor.CUSTOMER))
    await session.commit()
    return await _load_full(session, order_id)


async def accept_by_restaurant(session: AsyncSession, user, order_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    sm.apply_transition(session, order, OrderStatus.RESTAURANT_ACCEPTED, Actor.RESTAURANT)
    await session.commit()
    return await _load_full(session, order_id)


async def reject_by_restaurant(session: AsyncSession, user, order_id: int, reason: str | None = None) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    current = OrderStatus(order.status)
    sm.apply_transition(session, order, OrderStatus.REJECTED, Actor.RESTAURANT, reason)
    order.cancelled_by = Actor.RESTAURANT.value
    order.cancel_reason = reason
    _record_refund(order, RefundStatus.FULL)  # kitchen rejection always refunds
    await session.commit()
    return await _load_full(session, order_id)


async def advance_status(session: AsyncSession, user, order_id: int, to: OrderStatus) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    current = OrderStatus(order.status)
    sm.apply_transition(session, order, to, Actor.RESTAURANT)
    if to == OrderStatus.CANCELLED:
        order.cancelled_by = Actor.RESTAURANT.value
        _record_refund(order, sm.refund_on_cancel(current, Actor.RESTAURANT))
    await session.commit()
    return await _load_full(session, order_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `... -m pytest tests/modules/orders/test_service_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/modules/orders/service.py tests/modules/orders/test_service_lifecycle.py
git commit -m "feat(orders): cancel/accept/reject/advance lifecycle service"
```

---

### Task 6: Restaurant-acceptance timeout function

**Files:**
- Modify: `src/modules/orders/service.py`
- Modify: `src/config.py` (add `restaurant_accept_timeout_seconds: int = 300`)
- Test: `tests/modules/orders/test_timeout.py`

**Interfaces:**
- Produces: `async def expire_pending_acceptances(session, now: datetime) -> int` — finds orders with `status == PAYMENT_SUCCESS` whose `updated_at` is older than `now - restaurant_accept_timeout_seconds`; transitions each to `CANCELLED` (actor SYSTEM, reason "restaurant acceptance timeout"), full refund; commits once; returns the count expired. `now` is injected (never `datetime.now()` inside).

- [ ] **Step 1: Add the setting**

In `src/config.py`, in the OTP/timeout area, add:

```python
    # Orders
    restaurant_accept_timeout_seconds: int = 300
```

- [ ] **Step 2: Write the failing test**

```python
# tests/modules/orders/test_timeout.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.modules.orders import service
from src.modules.orders.models import Actor, Order, OrderStatus, RefundStatus
from src.modules.orders.state_machine import apply_transition


async def _payment_success_order(session, updated_delta_seconds: int):
    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value, subtotal=Decimal("20"), total=Decimal("20"))
    session.add(order)
    await session.flush()
    apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
    apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM)
    order.updated_at = datetime.now(timezone.utc) - timedelta(seconds=updated_delta_seconds)
    await session.commit()
    return order


@pytest.mark.asyncio
async def test_expire_past_window(db_session):
    order = await _payment_success_order(db_session, updated_delta_seconds=1000)
    count = await service.expire_pending_acceptances(db_session, now=datetime.now(timezone.utc))
    assert count == 1
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    assert order.refund_status == RefundStatus.FULL


@pytest.mark.asyncio
async def test_within_window_untouched(db_session):
    order = await _payment_success_order(db_session, updated_delta_seconds=10)
    count = await service.expire_pending_acceptances(db_session, now=datetime.now(timezone.utc))
    assert count == 0
    await db_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_SUCCESS
```

- [ ] **Step 3: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_timeout.py -v`
Expected: FAIL — `AttributeError: ... 'expire_pending_acceptances'`.

- [ ] **Step 4: Implement (append to `service.py`)**

```python
from datetime import datetime, timedelta  # add to imports
from src.config import settings  # add to imports


async def expire_pending_acceptances(session: AsyncSession, now: datetime) -> int:
    cutoff = now - timedelta(seconds=settings.restaurant_accept_timeout_seconds)
    stmt = select(Order).where(
        Order.status == OrderStatus.PAYMENT_SUCCESS.value,
        Order.updated_at < cutoff,
    )
    stale = list(await session.scalars(stmt))
    for order in stale:
        sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.SYSTEM,
                            reason="restaurant acceptance timeout")
        order.cancelled_by = Actor.SYSTEM.value
        _record_refund(order, RefundStatus.FULL)
    await session.commit()
    return len(stale)
```

- [ ] **Step 5: Run to verify pass**

Run: `... -m pytest tests/modules/orders/test_timeout.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/modules/orders/service.py src/config.py tests/modules/orders/test_timeout.py
git commit -m "feat(orders): restaurant-acceptance timeout sweep (logic only)"
```

---

### Task 7: Router + app wiring

**Files:**
- Create: `src/modules/orders/router.py`
- Modify: `src/main.py` (import + `app.include_router(orders_router)`)
- Test: `tests/modules/orders/test_api.py`

**Interfaces:**
- Consumes: all `service.*` functions; `OrderRead`, `OrderSummary` schemas; `CheckoutRequest`; `get_current_user`, `require_role`; `OrderStatus`.
- Produces routes:
  - `POST /orders/checkout` → 201, `OrderRead` (customer).
  - `GET /orders` → `list[OrderSummary]` (customer; `limit`/`offset` query).
  - `GET /orders/{id}` → `OrderRead`.
  - `POST /orders/{id}/cancel` → `OrderRead` (customer).
  - `POST /orders/{id}/accept` → `OrderRead` (restaurant/admin).
  - `POST /orders/{id}/reject` → `OrderRead` (body `{reason?: str}`).
  - `POST /orders/{id}/status` → `OrderRead` (body `{to: OrderStatus}`).
  - `POST /orders/internal/expire-acceptances` → `{expired: int}` (admin), uses `_utcnow()`.

- [ ] **Step 1: Write the failing end-to-end test**

```python
# tests/modules/orders/test_api.py
import pytest

from src.modules.orders.models import OrderStatus


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _seed(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559300001")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559300002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 2}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return owner, cust, addr, ph


@pytest.mark.asyncio
async def test_full_order_lifecycle(api_client):
    owner, cust, addr, ph = await _seed(api_client)
    order = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()
    oid = order["id"]

    assert (await api_client.post(f"/orders/{oid}/accept", headers=owner)).json()["status"] == OrderStatus.RESTAURANT_ACCEPTED.value
    for to in ["PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED"]:
        r = await api_client.post(f"/orders/{oid}/status", json={"to": to}, headers=owner)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == to

    # customer sees it in history
    hist = (await api_client.get("/orders", headers=cust)).json()
    assert any(o["id"] == oid for o in hist)


@pytest.mark.asyncio
async def test_customer_cancel_and_ownership(api_client):
    owner, cust, addr, ph = await _seed(api_client)
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph}, headers=cust)).json()["id"]
    # another customer cannot view it
    other = await _login(api_client, "customer", "c2@x.com", "+15559300003")
    assert (await api_client.get(f"/orders/{oid}", headers=other)).status_code == 403
    # owner cannot skip straight to DELIVERED
    assert (await api_client.post(f"/orders/{oid}/status", json={"to": "DELIVERED"}, headers=owner)).status_code == 409
    # customer cancels (pre-prep) → full refund
    c = (await api_client.post(f"/orders/{oid}/cancel", headers=cust)).json()
    assert c["status"] == OrderStatus.CANCELLED.value and c["refund_status"] == "FULL"


@pytest.mark.asyncio
async def test_checkout_requires_auth(api_client):
    assert (await api_client.post("/orders/checkout", json={"address_id": 1, "price_hash": "x"})).status_code == 401
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/modules/orders/test_api.py -v`
Expected: FAIL — 404s (routes not registered).

- [ ] **Step 3: Implement the router**

```python
# src/modules/orders/router.py
"""HTTP routes for the orders domain."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.infrastructure.redis import get_redis
from src.modules.cart.schemas import CheckoutRequest
from src.modules.orders import service
from src.modules.orders.models import OrderStatus, User_placeholder if False else None  # noqa
from src.modules.orders.schemas import OrderRead, OrderSummary
from src.modules.users.dependencies import get_current_user, require_role
from src.modules.users.models import User

router = APIRouter(prefix="/orders", tags=["orders"])


class RejectBody(BaseModel):
    reason: str | None = None


class StatusBody(BaseModel):
    to: OrderStatus


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout(data: CheckoutRequest, user: User = Depends(get_current_user),
                   session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.create_order_from_checkout(redis, session, user, data)


@router.get("", response_model=list[OrderSummary])
async def list_my_orders(limit: int = 20, offset: int = 0,
                         user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return await service.list_orders(session, user.id, limit, offset)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: int, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_db)):
    return await service.get_order_for_user(session, user, order_id)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(order_id: int, user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_db)):
    return await service.cancel_by_customer(session, user, order_id)


@router.post("/{order_id}/accept", response_model=OrderRead)
async def accept_order(order_id: int, user: User = Depends(require_role("restaurant", "admin")),
                       session: AsyncSession = Depends(get_db)):
    return await service.accept_by_restaurant(session, user, order_id)


@router.post("/{order_id}/reject", response_model=OrderRead)
async def reject_order(order_id: int, body: RejectBody = RejectBody(),
                       user: User = Depends(require_role("restaurant", "admin")),
                       session: AsyncSession = Depends(get_db)):
    return await service.reject_by_restaurant(session, user, order_id, body.reason)


@router.post("/{order_id}/status", response_model=OrderRead)
async def set_status(order_id: int, body: StatusBody,
                     user: User = Depends(require_role("restaurant", "admin")),
                     session: AsyncSession = Depends(get_db)):
    return await service.advance_status(session, user, order_id, body.to)


@router.post("/internal/expire-acceptances")
async def expire_acceptances(user: User = Depends(require_role("admin")),
                             session: AsyncSession = Depends(get_db)):
    count = await service.expire_pending_acceptances(session, now=datetime.now(timezone.utc))
    return {"expired": count}
```

> Cleanup: delete the bogus `User_placeholder ...` import line above — it is a guard against copy-paste; the real imports are `OrderStatus` from `orders.models` and `User` from `users.models`. Final import line should read: `from src.modules.orders.models import OrderStatus`.

- [ ] **Step 4: Wire the router in `main.py`**

Add near the other router imports:

```python
from src.modules.orders.router import router as orders_router
```

And after `app.include_router(cart_router)`:

```python
app.include_router(orders_router)
```

- [ ] **Step 5: Run the orders API tests**

Run: `... -m pytest tests/modules/orders/ -v`
Expected: PASS (including `test_service_create.py::test_create_order_from_checkout_persists_everything`, now that the route exists).

- [ ] **Step 6: Run the full suite (regression)**

Run: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret .venv/Scripts/python -m pytest -q`
Expected: all previous 72 tests still pass + new orders tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/modules/orders/router.py src/main.py tests/modules/orders/test_api.py
git commit -m "feat(orders): HTTP router and app wiring"
```

---

### Task 8: Alembic migrations + drop runtime create_all

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`
- Modify: `src/main.py` (remove the `create_all` call from lifespan)
- Modify: `requirements.txt` + `pyproject.toml` (add `alembic==1.14.0`)
- Modify: `README.md` (document `alembic upgrade head`)

**Interfaces:**
- Consumes: `Base.metadata` with all model modules imported; `settings.database_url`.
- Produces: a working `alembic upgrade head` that creates `users, addresses, restaurants, menu_categories, menu_items, orders, order_items, order_status_events`.

- [ ] **Step 1: Add the dependency**

Add `alembic==1.14.0` to `requirements.txt` (under the DB section) and to `pyproject.toml` `dependencies`. Install: `.venv/Scripts/python -m pip install alembic==1.14.0`.

- [ ] **Step 2: Create `alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 3: Create `alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create `alembic/env.py` (sync psycopg2 engine, converts +asyncpg away)**

```python
"""Alembic environment — runs migrations with a synchronous engine."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.config import settings
from src.infrastructure.database import Base

# Import every model module so Base.metadata is complete.
import src.modules.users.models  # noqa: F401
import src.modules.restaurants.models  # noqa: F401
import src.modules.orders.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    # Alembic uses a sync driver; strip any async driver qualifier.
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Autogenerate the initial migration against a scratch Postgres**

Bring up Postgres (`docker compose up -d postgres`) and run:

```bash
DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery \
  JWT_SECRET_KEY=x REDIS_URL=redis://localhost:6379/0 \
  .venv/Scripts/alembic revision --autogenerate -m "initial schema" --rev-id 0001
```

Review the generated `alembic/versions/0001_initial.py`: it must `create_table` for all 8 tables with matching columns/indexes. Fix the filename to `0001_initial.py` if needed.

- [ ] **Step 6: Verify upgrade + downgrade on a clean DB**

```bash
DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery JWT_SECRET_KEY=x REDIS_URL=redis://localhost:6379/0 .venv/Scripts/alembic upgrade head
DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery JWT_SECRET_KEY=x REDIS_URL=redis://localhost:6379/0 .venv/Scripts/alembic downgrade base
DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery JWT_SECRET_KEY=x REDIS_URL=redis://localhost:6379/0 .venv/Scripts/alembic upgrade head
```

Expected: no errors; `\dt` in psql shows all 8 tables after `upgrade head` and none after `downgrade base`.

- [ ] **Step 7: Remove `create_all` from the app lifespan**

In `src/main.py` lifespan, delete:

```python
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

Leave the model imports. (Tests keep their own `create_all` in `conftest.py` — do not touch that.)

- [ ] **Step 8: Confirm the app still boots and full suite passes**

Run: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret .venv/Scripts/python -c "import src.main"`
Then: `DATABASE_URL=sqlite+aiosqlite:///:memory: REDIS_URL=redis://localhost:6379/0 JWT_SECRET_KEY=test-secret .venv/Scripts/python -m pytest -q`
Expected: import clean; all tests pass.

- [ ] **Step 9: Document + commit**

Add to `README.md` a "Database migrations" note: run `alembic upgrade head` before starting the API; docker-compose should run it as a start step. Then:

```bash
git add alembic.ini alembic/ requirements.txt pyproject.toml src/main.py README.md
git commit -m "feat(orders): add Alembic migrations; drop runtime create_all"
```

---

## Self-Review

**Spec coverage:**
- Data model (Order/OrderItem/OrderStatusEvent + enums) → Task 1. ✅
- State machine + illegal-transition rejection → Task 2 + verified in Task 7 (409 on skip). ✅
- Cancellation/refund matrix (COD record-only) → Task 2 (rules) + Task 5 (application) + tests. ✅
- Checkout persists order, clears cart, double-submit lock → Task 3. ✅
- Order history + detail with ownership → Task 4. ✅
- Restaurant accept/reject + timeout logic (not scheduled) → Task 5 + Task 6 + internal endpoint in Task 7. ✅
- Endpoints table → Task 7. ✅
- Alembic + drop create_all → Task 8. ✅
- Error handling (OrderError codes, 404/403/409) → Tasks 2/4/5/7. ✅
- Testing strategy (unit + API on sqlite/fakeredis) → every task. ✅

**Placeholder scan:** The only intentional placeholder is the guard line in Task 7 Step 3, explicitly flagged for deletion with the correct final import stated. No TBD/TODO left in implementation code.

**Type consistency:** `apply_transition(session, order, to, actor, reason)`, `refund_on_cancel(current, actor)`, `customer_cancel_allowed(current)`, `create_order_from_checkout(redis, session, user, request)`, `get_order_for_user(session, user, order_id)`, `expire_pending_acceptances(session, now)` — signatures match between their producing task and every consuming task/router. Enum member access (`.value` when writing to `String` columns, bare member when comparing) is consistent throughout.

## Execution Handoff

Two execution options:
1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

# Orders Module — Design Spec

**Date:** 2026-07-28
**Status:** Approved for implementation
**Roadmap item:** 1 of 7 (Orders module + Alembic)
## 1. Purpose & Scope

Turn the dead-end checkout into a real order flow. Today `POST /cart/checkout`
validates the cart through the 5-gate pipeline and then **discards** the
resulting `ValidatedOrder` (`src/modules/cart/checkout.py`). This slice
persists that validated order, enforces the full order state machine, and
implements the cancellation/refund matrix from `docs/architecture-overview.md`
§5 — for **Cash-on-Delivery only**. It also introduces Alembic so schema
changes stop relying on `Base.metadata.create_all`.

### In scope
- New `orders` domain module: models, schemas, service, state machine, router.
- Persisting an order (+ item snapshot + first status event) from checkout.
- Full order state machine with centrally-validated transitions.
- Cancellation & refund matrix (COD-adapted: **refund is recorded, not charged**).
- Restaurant accept/reject endpoints + auto-cancel-on-timeout **logic**.
- Order history + order detail (with status timeline) endpoints.
- Alembic wired to the async engine with an initial migration covering existing
  (users, restaurants) + new (orders) tables.
- Unit + API tests matching current discipline (~91% coverage on the module).

### Explicitly out of scope (deferred, with clear seams)
- **(A) Real money movement.** COD collects nothing up front, so "refund" here
  sets `refund_status`/`refund_amount` + logs an event. The future **Payments**
  module (roadmap item 2) executes real refunds/PSP calls.
- **(B) A live scheduler.** The restaurant-acceptance timeout is implemented as
  a pure, tested function plus an internal trigger endpoint. No Cloud
  Scheduler / Cloud Tasks / background cron is wired this slice — that lands
  with Delivery/Ops.
- Online payment, driver assignment, notifications, Kafka/outbox events.

## 2. Data Model (new tables, `orders` module)

All money is `Numeric(10, 2)`, consistent with `restaurants/models.py`.

### `Order`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `customer_id` | int FK → users.id | indexed |
| `restaurant_id` | int FK → restaurants.id | indexed |
| `address_id` | int FK → users addresses.id | snapshot ref |
| `status` | Enum(OrderStatus) | see §3 |
| `payment_method` | Enum(PaymentMethod) | `COD` only for now |
| `payment_status` | Enum(PaymentStatus) | `PENDING`/`SUCCESS`/`FAILED`/`REFUNDED` |
| `subtotal` | Numeric(10,2) | from validated order |
| `delivery_fee` | Numeric(10,2) | flat/zero for MVP |
| `total` | Numeric(10,2) | subtotal + delivery_fee |
| `refund_status` | Enum(RefundStatus) | `NONE`/`FULL`/`PARTIAL` |
| `refund_amount` | Numeric(10,2) | default 0 |
| `cancelled_by` | Enum(Actor) nullable | `CUSTOMER`/`RESTAURANT`/`SYSTEM` |
| `cancel_reason` | String nullable | |
| `created_at` / `updated_at` | DateTime(tz) | |

### `OrderItem` (immutable price snapshot)
`id`, `order_id` FK, `menu_item_id`, `name`, `unit_price` Numeric(10,2),
`quantity` int, `line_total` Numeric(10,2). Snapshotted at checkout so later
menu edits never mutate order history.

### `OrderStatusEvent` (append-only audit / timeline)
`id`, `order_id` FK, `from_status` nullable, `to_status`, `actor`
Enum(Actor), `reason` nullable, `at` DateTime(tz). One row per transition;
powers the order-detail timeline and honest state history.

> **Cross-domain references stay by ID** (no cross-schema FK aspirations
> beyond what already exists). Consistent with the current single-`public`
> reality; a schema-per-domain refactor is a separate roadmap concern.

## 3. State Machine

Canonical lifecycle (docs §5):

```
CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS → RESTAURANT_ACCEPTED
        → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED → COMPLETED
```

Terminal: `COMPLETED`, `CANCELLED`, `REJECTED`.

- A single `transition(session, order, to, actor, reason)` validates `to`
  against an `ALLOWED: dict[OrderStatus, set[OrderStatus]]` map. Illegal or
  skipping transitions raise `ConflictException` (→ HTTP 409). Never mutate
  `status` outside this function.
- Every successful transition appends an `OrderStatusEvent` in the **same DB
  transaction** as the status write.
- **COD:** on order creation the flow auto-advances `CREATED →
  PAYMENT_PENDING → PAYMENT_SUCCESS`, with `payment_status=SUCCESS` meaning
  "to be collected on delivery" (recorded, not charged). This keeps COD on the
  same state path as a future online flow.
- `CANCELLED`/`REJECTED`/`COMPLETED` accept no outgoing transitions.

## 4. Cancellation & Refund (COD-adapted)

Refund here = set `refund_status` + `refund_amount` + log event. No PSP call.

| Cancel from state | Who | Result |
|---|---|---|
| `CREATED`, `PAYMENT_PENDING`, `PAYMENT_SUCCESS`, `RESTAURANT_ACCEPTED` (pre-prep) | Customer | `CANCELLED`, `refund_status=FULL`, `refund_amount=total` |
| `PREPARING` onward | Customer | **Rejected** (409) — needs restaurant/support approval |
| `PREPARING` onward | Restaurant/admin (approval) | `CANCELLED`, `refund_status=NONE` (food-cost forfeit) |
| Any state, system-caused | System | `CANCELLED`/`REJECTED`, `refund_status=FULL` |

System-caused reasons (always full refund): kitchen rejection, restaurant
acceptance timeout, no driver available, payment/system failure.

## 5. Restaurant Accept/Reject + Timeout

- `POST /orders/{id}/accept` → `PAYMENT_SUCCESS → RESTAURANT_ACCEPTED`
  (restaurant/admin, ownership-checked via existing
  `restaurants.service.owned_restaurant`).
- `POST /orders/{id}/reject` → `REJECTED`, `refund_status=FULL`,
  `cancelled_by=RESTAURANT`.
- **Timeout (built, not scheduled):** pure function
  `expire_pending_acceptances(session, now)` that finds orders stuck in
  `PAYMENT_SUCCESS` past `RESTAURANT_ACCEPT_TIMEOUT_SECONDS` and transitions
  them to `CANCELLED` (system-caused, full refund). Exposed via an internal
  endpoint `POST /orders/internal/expire-acceptances` for manual/cron
  triggering later. `now` is injected (never `datetime.now()` inside the pure
  logic) so it is deterministically testable.

## 6. Endpoints (`orders/router.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/orders/checkout` | customer | Run 5-gate validator, **persist** order+items+first event. Redis double-submit lock per user. |
| GET | `/orders` | customer | Caller's order history (paginated, newest first). |
| GET | `/orders/{id}` | customer/owner/admin | Order detail + status timeline; ownership-checked. |
| POST | `/orders/{id}/cancel` | customer | Customer cancellation (matrix §4). |
| POST | `/orders/{id}/accept` | restaurant/admin | Accept order. |
| POST | `/orders/{id}/reject` | restaurant/admin | Reject order (full refund). |
| POST | `/orders/{id}/status` | restaurant/admin | Advance status (PREPARING → … → DELIVERED/COMPLETED) via state machine. |
| POST | `/orders/internal/expire-acceptances` | admin/internal | Trigger timeout sweep. |

`/orders/checkout` **replaces** the persistence gap; the existing
`cart/checkout.py` validator is reused unchanged (it already returns a
`ValidatedOrder`). The cart is cleared on successful order creation.

## 7. Alembic

- Add `alembic/`, `alembic.ini`, `alembic/env.py` importing `Base.metadata`
  and all model modules; run migrations against the async engine URL (sync
  driver for autogenerate/upgrade).
- One initial migration: users + restaurants (existing) + orders (new).
- `src/main.py` stops calling `Base.metadata.create_all` in lifespan
  (production applies migrations). **Tests keep** `create_all` on
  SQLite/in-memory via `tests/conftest.py` — no migration run in the test path.
- Document `alembic upgrade head` in README / deploy notes.

## 8. Error Handling

- Illegal transition → `ConflictException` (409).
- Cancel not permitted from current state → `ConflictException` (409) with a
  machine code (`CANCEL_NOT_ALLOWED`).
- Order not found / not owned → `NotFoundException` (404) /
  `ForbiddenException` (403), reusing existing exception types.
- Double-submit checkout → second concurrent request rejected via Redis lock
  (`ConflictException`, code `CHECKOUT_IN_PROGRESS`).
- Checkout gate failures continue to surface the existing `CheckoutError`
  codes unchanged.

## 9. Testing Strategy (TDD)

Unit (no infra):
- Transition map: every legal edge succeeds; a representative set of illegal /
  skip edges raise 409; terminals reject all outgoing.
- Cancellation/refund matrix: each row (pre-prep customer, post-prep customer
  rejected, restaurant approval, system-caused).
- Timeout function: order past window → cancelled+full refund; within window →
  untouched; deterministic via injected `now`.

API (TestClient + in-memory DB + fakeredis, matching current conftest):
- Full happy path: add to cart → checkout → order persisted (row + items +
  event) → accept → status walk → DELIVERED → COMPLETED.
- Cart cleared after successful checkout.
- Each cancel branch end-to-end, ownership 403s, unauth 401s, not-found 404s.
- Checkout still enforces all 5 gates (regression).

Coverage goal: ~91% on `orders/` module, consistent with existing modules.

## 10. Non-Goals / Follow-ups (tracked for later roadmap items)
- Real refund execution + online payments → Payments slice.
- Live timeout scheduler + driver assignment + notifications → Delivery/Ops.
- Kafka/outbox events on status changes → Delivery/Ops.
- Schema-per-domain physical isolation → separate refactor.

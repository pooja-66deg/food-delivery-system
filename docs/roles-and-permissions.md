# Roles & Permissions

Who can do what in the Food Delivery System, and the exact criteria the backend
enforces. This reflects the implemented code (`src/modules/*`), not an aspiration.

## Roles

| Role | How it's created | Purpose |
|------|------------------|---------|
| **customer** | Public sign-up (default) | Browse, order, track, pay (COD) |
| **restaurant** | Public sign-up (choose "restaurant") | Own restaurants, manage menus, handle orders |
| **driver** | Public sign-up (choose "driver") | Pick up and deliver assigned orders |
| **admin** | **Not** self-service — provision by promoting a user in the DB (`UPDATE users SET role='admin' WHERE email=…`) | Platform oversight; elevated access everywhere |

A user has exactly one role, stored on `users.role`.

## How permissions are enforced

Four mechanisms, all in the backend:

1. **Authentication** — `get_current_user` requires a valid, non-expired **access** JWT for an active user. Missing/invalid/expired → `401`.
2. **Role gate** — `require_role(*roles)` allows the request only if `user.role` is in the listed roles; otherwise `403`.
3. **Restaurant ownership** — `owned_restaurant(user, restaurant_id)`: `404` if the restaurant doesn't exist; `403` unless the user is the **owner** *or* an **admin**.
4. **Order visibility** — `get_order_for_user(user, order_id)`: allowed if the user is the order's **customer**, owns the order's **restaurant**, or is an **admin**; else `403` / `404`.

The **order state machine** adds a fifth layer: even with the right role, a status change is rejected (`409`) if the transition is illegal (e.g. skipping states), and a customer cancellation is rejected once preparation has started.

---

## Capability matrix

✅ allowed · ⚠️ conditional (see notes) · — not allowed

| Capability | Customer | Restaurant | Driver | Admin |
|------------|:--------:|:----------:|:------:|:-----:|
| Register / login / OTP / refresh / logout | ✅ | ✅ | ✅ | ✅ |
| Manage own profile & addresses | ✅ | ✅ | ✅ | ✅ |
| Browse restaurants & menus (public) | ✅ | ✅ | ✅ | ✅ |
| Cart: add / update / remove / clear | ✅ | — | — | — |
| Place an order (checkout, COD) | ✅ | — | — | — |
| View **own** order history | ✅ | — | — | — |
| View a specific order's detail | ✅ own | ✅¹ | — | ✅ (any) |
| Cancel own order (before preparing) | ✅ | — | — | — |
| View order payment | ⚠️² | ⚠️² | — | ✅ (any) |
| Own notifications | ✅ | ✅ | ✅ | ✅ |
| Create a restaurant | — | ✅ | — | ✅ |
| Edit restaurant / open-close | — | ⚠️³ own | — | ✅ (any) |
| Manage menu (categories, items, availability) | — | ⚠️³ own | — | ✅ (any) |
| Accept / reject an order | — | ⚠️³ own | — | ✅ (any) |
| Advance order status (→ preparing … delivered) | — | ⚠️³ own | — | ✅ (any) |
| See driver assignments | — | — | ✅ own | ✅ |
| Pick up / deliver an order | — | — | ⚠️⁴ assigned | ✅ |
| Admin dashboard (stats, all users, all orders) | — | — | — | ✅ |
| Force-cancel any order | — | — | — | ✅ |
| Run the acceptance-timeout sweep | — | — | — | ✅ |

**Notes**
1. ⚠️¹ A restaurant sees an order's detail only if the order belongs to a restaurant it owns.
2. ⚠️² Viewing a payment reuses order visibility — you can see it only for an order you're allowed to see.
3. ⚠️³ A restaurant may act only on **its own** restaurants/orders (ownership check). An admin may act on **any**.
4. ⚠️⁴ A driver may pick up/deliver only an order whose delivery is **assigned to that driver**.

> **Cart & customer-order endpoints are role-locked to `customer`.** `all /cart…`, `POST /orders/checkout`, `GET /orders`, and `POST /orders/{id}/cancel` require the customer role — other roles receive `403`. (Viewing a single order via `GET /orders/{id}` stays open to the customer, the owning restaurant, or an admin.)

---

## By role

### Customer
- **Account:** register (default role), log in by password or OTP, refresh/logout, manage profile and delivery addresses.
- **Browse:** list/search restaurants and view menus.
- **Cart & checkout:** add/update/remove items (one restaurant per cart), then `POST /orders/checkout` — runs the 5 validation gates (restaurant open, items available, price unchanged, address in the restaurant's city, minimum order met) and creates a **Cash-on-Delivery** order.
- **Track:** `GET /orders` and `GET /orders/{id}` (own only) with a status timeline; `GET /payments/order/{id}`; `GET /notifications`.
- **Cancel:** `POST /orders/{id}/cancel` — allowed only in the pre-preparation states (`CREATED`, `PAYMENT_PENDING`, `PAYMENT_SUCCESS`, `RESTAURANT_ACCEPTED`); yields a full refund. After preparation starts it's rejected (`409`) and needs restaurant/support.
- **UI:** Restaurants, Cart, Orders, Account.

### Restaurant
- **Account:** register as "restaurant", same auth/profile features.
- **Restaurants:** `POST /restaurants` (create); `PATCH /restaurants/{id}` to edit details and toggle **open/closed** — own only.
- **Menu:** add categories, add/edit menu items, toggle item availability — own only.
- **Orders:** `POST /orders/{id}/accept`, `/reject` (full refund), and `/status` to advance through `PREPARING → READY_FOR_PICKUP → …` — own restaurant's orders only. Illegal jumps are rejected (`409`).
- **UI:** Restaurants, **Manage** (create + menu management), Account.

### Driver
- **Account:** register as "driver" (the **Driver** tab on the sign-up screen).
- **Assignments:** a driver is **auto-assigned** an order when the restaurant marks it `READY_FOR_PICKUP` (one active order per driver). `GET /delivery/assignments` lists active ones.
- **Deliver:** `POST /delivery/orders/{id}/pickup` (→ order `OUT_FOR_DELIVERY`) and `/deliver` (→ order `DELIVERED`, payment settled) — only for orders assigned to that driver.
- **UI:** a **Deliveries** screen listing active assignments with Pick up / Mark delivered actions.

### Admin
- **Everything a restaurant can do, on any restaurant**, and **view/act on any order** (accept, reject, advance, force-cancel via `/orders/{id}/status → CANCELLED`).
- **Dashboard:** `GET /admin/stats` (counts + GMV + orders-by-status), `GET /admin/users`, `GET /admin/orders`.
- **Operations:** `POST /admin/expire-acceptances` — runs the restaurant-acceptance timeout sweep (auto-cancel + full refund of orders the restaurant never accepted in time).
- **UI:** an **Admin** console (Overview / Orders / Users) with a force-cancel action and the timeout-sweep button.
- **Cannot:** self-register (must be provisioned in the DB). Has no customer cart/orders UI.

---

## Order lifecycle & who drives each step

```
CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS → RESTAURANT_ACCEPTED
        → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED → COMPLETED
Terminal: COMPLETED · CANCELLED · REJECTED
```

| Transition | Who performs it |
|------------|-----------------|
| `CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS` | System (automatic at checkout; COD marked "to collect") |
| `PAYMENT_SUCCESS → RESTAURANT_ACCEPTED` / `REJECTED` | Restaurant (or admin) |
| `RESTAURANT_ACCEPTED → PREPARING → READY_FOR_PICKUP` | Restaurant (or admin) |
| `READY_FOR_PICKUP → OUT_FOR_DELIVERY` | Driver (pickup) |
| `OUT_FOR_DELIVERY → DELIVERED` | Driver (deliver) — settles the COD payment |
| `DELIVERED → COMPLETED` | Restaurant/admin |
| `→ CANCELLED` (customer) | Customer, pre-preparation only — full refund |
| `→ CANCELLED` (restaurant/admin, after prep) | Restaurant/admin — **no** refund (food-cost forfeit) |
| `→ CANCELLED` (timeout / system) | System sweep — full refund |

## Refund rules (COD — recorded, not charged in this MVP)

| Cancelled from | By | Refund |
|----------------|----|--------|
| Pre-preparation states | Customer | Full |
| Any pre-prep state | Restaurant/admin | Full |
| `PREPARING` onward | Restaurant/admin | None (food-cost forfeit) |
| Any non-terminal state | System (kitchen reject, acceptance timeout) | Full |

Refunds set `refund_status`/`refund_amount` and mark the payment `REFUNDED`; real money movement is handled by the Payments module's provider (COD collects nothing up front, so it's a bookkeeping void).

---

## Endpoint reference (by access level)

| Access | Endpoints |
|--------|-----------|
| **Public** | `GET /`, `/health`, `/docs`; `POST /auth/register`, `/auth/login`, `/auth/otp/request`, `/auth/otp/verify`, `/auth/refresh`, `/auth/logout`; `GET /restaurants`, `/restaurants/{id}`, `/restaurants/{id}/categories` |
| **Any authenticated user** | `GET/PATCH /users/me`; `GET/POST/DELETE /users/me/addresses…`; `GET /notifications`; `GET /orders/{id}` and `GET /payments/order/{id}` (subject to order visibility) |
| **Customer only** | all `/cart…`; `POST /orders/checkout`; `GET /orders`; `POST /orders/{id}/cancel` |
| **Restaurant / admin** | `POST /restaurants`; `PATCH /restaurants/{id}`; `POST /restaurants/{id}/categories`; `POST/PATCH/DELETE /restaurants/{id}/items…`; `POST /orders/{id}/accept`, `/reject`, `/status` |
| **Driver / admin** | `GET /delivery/assignments`; `POST /delivery/orders/{id}/pickup`, `/deliver` |
| **Admin only** | `GET /admin/stats`, `/admin/users`, `/admin/orders`; `POST /admin/expire-acceptances`; `POST /orders/internal/expire-acceptances` |

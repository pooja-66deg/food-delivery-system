# Roles & Permissions

Who can do what in the Food Delivery System, and the exact criteria the backend
enforces. This reflects the implemented code (`src/modules/*`), not an aspiration.

## Roles

| Role | How it's created | Purpose |
|------|------------------|---------|
| **customer** | Public sign-up (default) | Browse, order, track, pay (COD) |
| **restaurant** | Public sign-up (choose "restaurant") — **the account is created inactive and cannot log in until an admin approves the venue** | Own restaurants, manage menus, handle orders |
| **driver** | Public sign-up (choose "driver") | Pick up and deliver assigned orders |
| **admin** | **Not** self-service — provision by promoting a user in the DB (`UPDATE users SET role='admin' WHERE email=…`) | Platform oversight; elevated access everywhere |

A user has exactly one role, stored on `users.role`.

### The restaurant approval gate

Restaurant is the one role that cannot sign in the moment it signs up, because
`restaurant` is self-service: without a gate, anyone could register and have a
listing taking orders and payments within a minute.

1. The sign-up form collects the **business** as well as the person — name,
   address, city, phone, food type — because there is no later session in which
   to supply it, and an admin approving a bare name and email would not be
   vetting a business.
2. The account is created with `is_active = false` and
   `approval_status = 'pending'`. Login refuses it and says why.
3. The venue is handed to the restaurants service on `restaurant-registrations`
   and appears in the admin console as pending. If `ADMIN_ALERT_EMAIL` is set,
   an alert is mailed there too.
4. An admin approves or rejects it. That decision travels back on
   `restaurant-events`; the users service consumes it and, on approval, sets
   `is_active = true`.
5. Notifications emails the owner the outcome — the only channel that reaches
   somebody the platform is currently keeping out.

A **rejection never deactivates an already-approved account**: it is a decision
about a listing, not a ban on a person, and by then the owner may have been
trading for a year.

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
| Register / login / refresh / logout | ✅ | ✅ | ✅ | ✅ |
| Manage own profile & addresses | ✅ | ✅ | ✅ | ✅ |
| Browse restaurants & menus (public) | ✅ | ✅ | ✅ | ✅ |
| Cart: add / update / remove / clear | ✅ | — | — | — |
| Place an order (checkout, COD) | ✅ | — | — | — |
| View **own** order history | ✅ | — | — | — |
| View a specific order's detail | ✅ own | ✅¹ | — | ✅ (any) |
| Cancel own order (before preparing) | ✅ | — | — | — |
| View order payment | ⚠️² | ⚠️² | — | ✅ (any) |
| Own notifications | ✅ | ✅ | ✅ | ✅ |
| Register a restaurant (one per account) | — | ✅ | — | — |
| Approve / reject a restaurant | — | — | — | ✅ |
| Set restaurant food type (veg / non-veg / both) | — | ⚠️³ own | — | ✅ (any) |
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
- **Account:** register (default role), log in by email and password, refresh/logout, manage profile and delivery addresses.
- **Browse:** list/search restaurants and view menus.
- **Cart & checkout:** add/update/remove items (one restaurant per cart), then `POST /orders/checkout` — runs the 5 validation gates (restaurant open, items available, price unchanged, address in the restaurant's city, minimum order met) and creates a **Cash-on-Delivery** order.
- **Track:** `GET /orders` and `GET /orders/{id}` (own only) with a status timeline; `GET /payments/order/{id}`; `GET /notifications`.
- **Cancel:** `POST /orders/{id}/cancel` — allowed only in the pre-preparation states (`CREATED`, `PAYMENT_PENDING`, `PAYMENT_SUCCESS`, `RESTAURANT_ACCEPTED`); yields a full refund. After preparation starts it's rejected (`409`) and needs restaurant/support.
- **UI:** Restaurants, Cart, Orders, Account.

### Restaurant
- **Account:** register as "restaurant", same auth/profile features.
- **Restaurants:** `POST /restaurants` registers **one** restaurant per account — a second returns `409`. It starts **pending** and is invisible to customers until an admin approves it; the owner sees it at `GET /restaurants/mine` meanwhile, with the rejection reason if there is one. `PATCH /restaurants/{id}` edits details, address, contact, food type and open/closed — own only, and none of it re-opens approval.
- **Menu:** add categories, add/edit menu items, toggle item availability — own only.
- **Orders:** `POST /orders/{id}/accept`, `/reject` (full refund), and `/status` to advance through `PREPARING → READY_FOR_PICKUP → …` — own restaurant's orders only. Illegal jumps are rejected (`409`).
- **UI:** Restaurants, **Manage** (registration when they have none, then menu, stock, address and settings), Account.

### Driver
- **Account:** register as "driver" (the **Driver** tab on the sign-up screen).
- **Assignments:** a driver is **auto-assigned** an order when the restaurant marks it `READY_FOR_PICKUP` (one active order per driver). `GET /delivery/assignments` lists active ones.
- **Deliver:** `POST /delivery/orders/{id}/pickup` (→ order `OUT_FOR_DELIVERY`) and `/deliver` (→ order `DELIVERED`, payment settled) — only for orders assigned to that driver.
- **UI:** a **Deliveries** screen listing active assignments with Pick up / Mark delivered actions.

### Admin
- **Everything a restaurant can do, on any restaurant**, and **view/act on any order** (accept, reject, advance, force-cancel via `/orders/{id}/status → CANCELLED`).
- **Restaurants:** `GET /restaurants/admin/all` lists every venue whatever its status — name, owner, city/address, contact, open/closed, approval status, rating, review count. `POST /restaurants/{id}/approval` approves or rejects one; a rejection carries a reason the owner is shown, and closes the venue.
- **Dashboard:** `GET /admin/stats` (counts + GMV + orders-by-status), `GET /admin/users`, `GET /admin/orders`.
- **Operations:** `POST /admin/expire-acceptances` — runs the restaurant-acceptance timeout sweep (auto-cancel + full refund of orders the restaurant never accepted in time).
- **UI:** an **Admin** console (Overview / Manage restaurants / Orders / Users) with approve-reject, a force-cancel action and the timeout-sweep button.
- **Cannot:** self-register (must be provisioned in the DB). Has no customer cart/orders UI. **Cannot register a restaurant** — owners do that for themselves, and a venue an operator created would have nobody to run it.

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
| **Public** | `GET /`, `/health`, `/docs`; `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`; `GET /restaurants`, `/restaurants/{id}`, `/restaurants/{id}/categories` |
| **Any authenticated user** | `GET/PATCH /users/me`; `GET/POST/DELETE /users/me/addresses…`; `GET /notifications`; `GET /orders/{id}` and `GET /payments/order/{id}` (subject to order visibility) |
| **Customer only** | all `/cart…`; `POST /orders/checkout`; `GET /orders`; `POST /orders/{id}/cancel` |
| **Restaurant / admin** | `POST /restaurants`; `PATCH /restaurants/{id}`; `POST /restaurants/{id}/categories`; `POST/PATCH/DELETE /restaurants/{id}/items…`; `POST /orders/{id}/accept`, `/reject`, `/status` |
| **Driver / admin** | `GET /delivery/assignments`; `POST /delivery/orders/{id}/pickup`, `/deliver` |
| **Admin only** | `GET /admin/stats`, `/admin/users`, `/admin/orders`; `POST /admin/expire-acceptances`; `POST /orders/internal/expire-acceptances` |

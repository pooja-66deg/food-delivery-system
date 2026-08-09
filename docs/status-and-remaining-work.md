# Status & Remaining Work

A full-codebase review as of **2026-08-04** (branch `main`, commit `57c5f77`): what is
actually built, what is verified working, and what is left — ordered by whether it
blocks a real deployment, hardening, or product completeness.

This document reflects the code, not the plan. Where the code and an existing doc
disagree, the disagreement is listed in §6. Features built after the initial review are
recorded in §7 and removed from the §5 gap list.

---

## 1. Verified state

Everything below was run against this working tree, not inferred:

| Check | Command | Result |
|-------|---------|--------|
| Backend unit tests | `pytest -m "not integration"` | **530 passed**, 1 deselected (4m11s) |
| Backend lint | `flake8 src` | **clean** |
| Frontend tests | `cd frontend && npm test` | **274 passed**, 32 files |
| Frontend type-check + build | `cd frontend && npm run build` | **clean** |
| Migration chain | `alembic history` / `heads` | linear, **single head** (0012) |
| Placeholder scan | grep for `TODO`/`FIXME`/`NotImplemented` in `src`, `frontend/src`, `infra` | **none** — no unfinished markers in implementation code |

Scale: ~6,600 lines of backend Python across 11 modules, 70 backend test files,
88 frontend source files, 35 frontend test files, 12 Alembic migrations.

> The Testcontainers migration check (`alembic upgrade head` / `downgrade base` /
> `upgrade head` against real Postgres) was **not** run locally — Docker is unavailable in
> this environment. CI runs it on every push.

The codebase is coherent and finished-feeling at the module level. What is missing is
almost entirely **operational**: the things that run *between* requests (schedulers,
relays, metrics) and the things that make a cloud deploy actually serve traffic.

---

## 2. What is built

### Backend modules (all wired into [src/main.py](../src/main.py))

| Module | State | Notes |
|--------|-------|-------|
| **users** | Complete | Email + password login, JWT access/refresh with revocation and session generation, profile, addresses (geocoded), rate-limited auth routes. No OTP, password reset or email verification — removed deliberately; a forgotten password is an operator task |
| **restaurants** | Complete | Profile, open/close, delivery radius, categories, menu items, per-item stock and vegetarian flag, image upload, dish-aware search with rating/price/dietary filters, sorting and paging, typeahead, popular cuisines, ownership gates |
| **cart** | Complete | Redis-backed cart, 5-gate checkout validation ([checkout.py](../src/modules/cart/checkout.py)) with stable machine-readable failure codes, reorder-from-past-order |
| **orders** | Complete | Validated state machine, per-transition event log, customer/restaurant/admin visibility rules, cancellation + refund rules, stock reserve/restore, acceptance-timeout and unpaid-order sweeps, per-user checkout lock |
| **payments** | Complete | COD lifecycle, real Stripe provider behind a `PaymentProvider` protocol with a deterministic stand-in when unkeyed, hand-rolled webhook signature verification with replay tolerance and event dedupe, resume/retry, refunds |
| **delivery** | Complete | Driver online/offline + Redis GEO, nearest-driver assignment, accept/reject with re-offer, pickup/deliver, live tracking with Google Routes ETA and a Haversine fallback, per-order ETA cache |
| **notifications** | Complete | In-app feed plus outbound email/SMS/push routed per status through the Twilio/SendGrid/FCM adapters, per-user channel preferences, device-token store, and a delivery audit trail |
| **reviews** | Complete | One review per delivered order, author edit/withdraw, admin moderation, restaurant owner reply, rating aggregation and breakdown, reviewer display name |
| **favorites** | Complete | Saved restaurants, idempotent add, per-user scoping |
| **admin** | Read-only | Stats + GMV, users list, orders list, timeout sweep trigger |
| **events** | Partially wired | `record_event` is called on every order status change; `relay_outbox` exists but **nothing calls it** — see §3.5 |

### Frontend

15 routes across customer, owner, driver, and admin surfaces; auth/cart/notifications
contexts; Stripe Elements card step; Google Maps delivery tracking with a text-only
fallback; a shared `ui/` primitive set. Order detail polls tracking every 5s,
notifications every 25s.

### Infrastructure

Docker Compose local stack (Postgres + Redis + API + nginx frontend), GitHub Actions CI
(lint → migration up/down/up → full pytest → frontend type-check + build), Cloud Build
pipeline (test → build → push → deploy two Cloud Run services), and a documented
one-time GCP setup.

---

## 3. Blockers — a cloud deploy will not work correctly until these are fixed

These are not "nice to have." Each one produces a visibly broken deployed app.

**3.1 and 3.2 are now fixed** (see below). 3.3–3.5 remain open, and 3.3 in particular is
worth knowing about before the first automatic deploy: uploaded images will not survive it.

### 3.1 `CORS_ORIGINS` on the deployed API — **FIXED**

The deploy step set only `ENVIRONMENT` and `KAFKA_BROKERS`, so the API fell back to its
localhost allowlist and every browser request from the deployed frontend (a separate
Cloud Run service on its own origin) was CORS-blocked.

Now set from a new `_FE_URL` substitution, supplied by the deploy job from the
`GCP_FE_URL` repository variable.

### 3.2 `FRONTEND_BASE_URL` on the deployed API — **FIXED**

Password-reset and email-verification links were built from a value defaulting to
`http://localhost:5173`, so production mailed recipients a link to their own machine.
Now set from the same `_FE_URL`.

### 3.3 Uploaded images are broken in production, twice over

Two independent faults:

1. **Storage is local disk.** [storage.py](../src/modules/restaurants/storage.py) writes
   under `settings.media_root` and `main.py` mounts it via `StaticFiles`. Cloud Run
   containers have ephemeral, per-instance filesystems — an upload vanishes on the next
   revision and is invisible to every other instance. The module docstring already
   anticipates this ("Swap `save_image` for a Cloud Storage / S3 upload later"); the
   architecture doc names Cloud Storage as the target.
2. **The URL is hardcoded to the dev proxy.** [Thumb.tsx:25](../frontend/src/components/ui/Thumb.tsx#L25)
   renders `src={`/api${url}`}`. In production that resolves against the *frontend*
   origin, which serves no `/api` path — so it 404s even if the file existed.

**Fix:** implement a GCS-backed `save_image` returning an absolute URL, and make `Thumb`
resolve relative paths against the API base rather than a literal `/api`.

### 3.4 Nothing runs the scheduled sweeps

Two time-based rules are implemented and tested, but only reachable by an authenticated
admin hitting an endpoint by hand:

- `POST /orders/internal/expire-acceptances` and `POST /admin/expire-acceptances` —
  auto-cancel + refund orders the restaurant never accepted within
  `RESTAURANT_ACCEPT_TIMEOUT_SECONDS`.
- `POST /orders/internal/expire-unpaid` — cancel card orders that sat unpaid past
  `PAYMENT_WINDOW_SECONDS` and release their stock reservation.

Until something invokes these on a schedule, unaccepted orders hang forever and unpaid
card orders hold stock indefinitely. The architecture doc already names the mechanism
(Cloud Scheduler); it has not been created.

**Fix:** two Cloud Scheduler jobs with OIDC auth against the `/internal/*` endpoints, or
an in-process background task if you prefer to avoid the auth plumbing.

### 3.5 The outbox is written but never relayed

`record_event` is called inside the same transaction as every order status change — the
hard half of the outbox pattern, done correctly. But `relay_outbox`
([outbox.py:17](../src/modules/events/outbox.py#L17)) has no caller anywhere in `src/` —
only in `tests/modules/events/test_outbox.py`.

Consequence today: `outbox_events` grows unboundedly with `published_at IS NULL` and no
event ever leaves the app. This is currently harmless *because* Kafka is disabled
everywhere (`KAFKA_BROKERS=disabled` in Compose and in the Cloud Run deploy) and nothing
consumes events — but the moment a broker is configured, the relay is the missing piece.

**Fix:** a scheduled relay (same mechanism as 3.4) or a lifespan background task, gated
on Kafka being enabled.

---

## 4. Hardening — Phase 4 and 5 of the implementation plan are largely unstarted

### 4.1 Observability: declared, not wired

`pyproject.toml` defines a `monitor` extra with `opentelemetry-api`,
`opentelemetry-sdk`, `opentelemetry-exporter-prometheus`, and `prometheus-client`.
**None of the four is imported anywhere in `src/`.** There is no `/metrics` endpoint,
no tracer, no span instrumentation, no request-id correlation, and logging is
`logging.basicConfig` with plain-text output rather than structured JSON that Cloud
Logging can index.

This is the single largest gap against the plan (Phase 4: "Logging and tracing",
"Monitoring dashboards") and against the architecture doc's Cloud Operations mapping.

**Work:** FastAPI + SQLAlchemy + httpx OTel instrumentation, a Prometheus exporter or
direct Cloud Monitoring export, structured JSON logs with a request-id middleware, and
at minimum these alerts: 5xx rate, p95 latency, checkout failure rate, payment-webhook
failure rate, unpublished-outbox depth.

### 4.2 Events: no consumer, no retry, no DLQ

Kafka is disabled by default and commented out of Compose
([docker-compose.yml:50-71](../infra/compose/docker-compose.yml#L50-L71)). Beyond the
un-called relay (§3.5), there is **no consumer of any kind**, no retry-with-backoff, and
no dead-letter topic — all three promised in architecture §8. The producer's failure
handling is a per-row `attempts` counter with no backoff and no cap.

**Decision needed first:** the app works fine without events today (every cross-domain
call is in-process). Either commit to Kafka/Pub-Sub and build consumer + retry + DLQ, or
formally defer it and mark the outbox as forward-looking. Right now it is in a third
state — half-built — which is the worst of the three.

### 4.3 No persisted saga state

Architecture §9 specifies an order-placement saga with persisted state and explicit
compensations. What exists is imperative compensation inside
`create_order_from_checkout` — correct for the current happy/unhappy paths, but with no
saga table, no resumability after a crash mid-placement, and no way to audit where a
half-placed order stalled.

### 4.4 Data isolation deviates from the architecture

Architecture §1 mandates **one Postgres schema per domain** with cross-schema foreign
keys disallowed, and calls it the thing that makes a future service split mechanical.
The implementation puts all 13 tables in the default `public` schema, and there are real
cross-domain foreign keys (`orders.customer_id → users.id`,
`orders.restaurant_id → restaurants.id`, `orders.address_id → addresses.id`,
`deliveries.order_id → orders.id`).

The module *code* boundaries are clean — no module queries another's tables. But the
database-level guarantee the doc promises is not there, so a service split would be a
migration project rather than a lift-out.

**Either** implement schema-per-domain in a migration and replace cross-domain FKs with
ID references, **or** amend architecture §1 to describe what was actually chosen. The
second is a legitimate call for a monolith; the drift is the problem.

### 4.5 Test coverage gaps

- **One integration test.** `tests/integration/test_postgres.py` is the entire
  Testcontainers suite. Nothing exercises the real Postgres/Redis path for the flows
  most likely to break there: concurrent checkout under the per-user lock, stock
  decrement races, Redis GEO assignment.
- ~~**CI does not run frontend tests.**~~ **Fixed** — `npm test` now runs in CI and gates
  the deploy.
- **Cloud Build does not run frontend tests** — `cloudbuild.yaml`'s `test` step is
  `pytest -q` only. Less pressing now that GitHub Actions gates every deploy, but a
  direct `gcloud builds submit` still bypasses the frontend suite.
- **No E2E test.** No Playwright/Cypress run of the register → order → deliver flow the
  README documents manually.
- **No load test.** The <300ms p95 target in architecture §10 has never been measured.

### 4.6 No production operations material

**Partly addressed:** there is now a CD pipeline (merge to `main` → test → build → deploy)
and a documented rollback-by-tag procedure, since images are tagged with the commit sha.

Phase 5 deliverables that still do not exist: staging environment, runbooks,
backup/PITR restore drill, Cloud Armor/WAF, autoscaling limits (Cloud Run
`--min-instances`/`--max-instances`/`--concurrency` are all unset, so an unbounded
autoscale can exhaust Cloud SQL connections), and health-check-driven readiness
(`/health` returns static JSON — it never checks Postgres or Redis, so a database
outage still reports healthy).

### 4.7 Unbounded queries

**Partly fixed** (see §7): the browse endpoint now pages, with a server-side cap, and
`list_restaurants` is gone — `discovery.search` replaced it. Still unbounded:
`suggest_restaurants` takes a caller-supplied limit but no floor on the query cost, and
the menu category/item listings on `GET /restaurants/{id}` return every row for the
restaurant. `admin` and `favorites` endpoints paginate. Menu size is owner-controlled, so
this is a smaller risk than the browse endpoint was, but it is the remaining unbounded
read on a p95-target path.

---

## 5. Product gaps

Not bugs — scope that a food-delivery platform is normally expected to have and this one
does not yet.

> **Shipped since this document was first written** (2026-08-04), so no longer gaps:
> radius-based delivery zones, outbound order notifications over email/SMS/push with
> per-user channel preferences, dish-level search with rating/price/dietary filters and
> sorting plus paged browse, review editing/deletion/owner replies, reorder, and
> favourites. See §7 for what those changed.

**Ordering itself** — the two biggest feature gaps in the platform
- **No item customization.** A cart line is `menu_item_id + quantity` and nothing else
  ([schemas.py:24](../src/modules/cart/schemas.py#L24)). There are no sizes, variants,
  option groups, or add-ons anywhere in the menu model — no "large", no "extra cheese",
  no "no onions". Real menus are priced by variant, so this affects the menu model, cart
  pricing, the price hash, and the order-item snapshot together.
- **No special instructions.** No free-text note field on a cart line, an order item, or
  the order — so no "no chilli", and no delivery instruction like "leave at the gate".
  Cheap to add and universally expected.

**Money**
- `delivery_fee` is hardcoded `Decimal("0")` at order creation. The column exists; nothing
  ever computes it. No distance- or zone-based fee.
- No taxes, no tips, no service fee, no promo/coupon codes, no wallet or credits.

**Restaurants**
- No opening hours — only an `is_open` boolean the owner toggles by hand. Architecture §2
  and §3 both name opening hours as in-scope.
- No restaurant approval/verification flow — a new signup can create a live restaurant
  and take orders immediately.
- Owning several restaurants works, but there is no "my restaurants" endpoint: the owner
  page fetches *every* restaurant and filters by `owner_id` in the browser
  ([OwnerPage.tsx:23-25](../frontend/src/pages/owner/OwnerPage.tsx#L23-L25)), which
  compounds the unbounded-query issue in §4.7.

**Discovery**
- No delivery-time filter (there is no per-restaurant prep-time estimate to filter on).
- No scheduled/future orders, no multi-restaurant cart.

**Reviews**
- No photos, no helpfulness votes, no moderation queue (an admin can delete, but there is
  nothing that surfaces what needs looking at).

**Drivers**
- No earnings view, no delivery history, no shift management beyond the online/offline
  flag (which lives only in Redis, so a cache flush silently marks everyone offline).
- One active order per driver by design — no batching.

**Notifications**
- Push has no browser-side registration yet: the API stores device tokens, but the SPA
  never asks for notification permission or obtains an FCM token, so no device is
  registered in practice.
- Delivery to the customer is HTTP polling (5s tracking, 25s notifications). No
  WebSocket/SSE — consistent with architecture §12a deferring real-time, but it means a
  fixed poll cost per open tab.

**Admin**
- Dashboard is read-only aggregation plus a force-cancel and the sweep button. No
  moderation, no refund override, no user suspension, no restaurant approval, no
  role management — admins are still provisioned by a manual `UPDATE users SET role=…`.

---

## 6. Documentation drift

Fix these while the details are fresh; each one currently misleads a reader.

| File | Problem |
|------|---------|
| [infra/gcp/README.md:105](../infra/gcp/README.md#L105) | "the API currently allows all origins (fine for MVP)" — false. `main.py` has had an explicit allowlist for some time. The real issue is the opposite one (§3.1). |
| [docs/roles-and-permissions.md](roles-and-permissions.md) | Claims to reflect implemented code, but predates most of what has shipped. Missing from the capability matrix and endpoint reference: CARD/Stripe payments (it says COD-only throughout), reviews and their edit/delete/reply rules, delivery tracking, driver accept/reject, driver location/online, password reset, email verification, change password, image upload, search/suggest/cuisines, `expire-unpaid`, notification preferences and devices, favourites, reorder, and the delivery radius. This is now the most out-of-date file in the repo. |
| [docs/architecture-overview.md:301](architecture-overview.md#L301) | "`pytest` reports **2 passed**" — the suite is now 369. §13's change log describes the scaffold-repair era and reads as current state. |
| [docs/README.md:9-10](README.md#L9-L10) | `api-design.md` and `database-schema.md` listed as "coming soon" — never written. `/docs` (Swagger) covers the first; the second has no equivalent. |
| [docs/implementation-plan.md](implementation-plan.md) | No status annotation anywhere. A reader cannot tell that Phases 0–3 are done and 4–5 are not. |

---

## 7. Shipped on 2026-08-04

Four feature sets from §5, built after the review above. Each is covered by unit and
API-level tests, and the design decisions worth knowing are recorded here because they
change how the system behaves rather than just adding surface.

### Delivery zones ([zones.py](../src/modules/restaurants/zones.py))

Checkout gate 4 now measures distance against a per-restaurant `delivery_radius_km`
instead of comparing city strings. Two behaviour changes, both intended: **same city, far
apart is now rejected** (the 40-km-across-one-city case), and **different cities, close
together is now accepted**. The radius only applies when both the restaurant and the
address are geocoded — either end being unmappable falls back to the old city match, so no
existing data breaks. A geocoded restaurant that never sets a radius gets
`DELIVERY_DEFAULT_RADIUS_KM` (10 km), not unlimited.

### Notification reach ([templates.py](../src/modules/notifications/templates.py), [preferences.py](../src/modules/notifications/preferences.py))

Order status changes now go out over email, SMS and push, not just the in-app feed.

- **Per-status channel policy**, so the platform is not spam: push on every status, SMS
  only for `OUT_FOR_DELIVERY`/`DELIVERED`/`CANCELLED`/`REJECTED`, email only for the
  confirmation and the final outcome.
- **Preferences** default to email and push on, SMS off — SMS is the one channel that
  costs per message, so it is opt-in.
- **Sends happen after the commit**, never inside the status-change transaction: a
  provider call has no business holding a transaction open, and a sent message cannot be
  rolled back. `_deliver_status` in the order service is called at the end of each
  lifecycle function for this reason.
- Outbound attempts are recorded as `Notification` rows with `delivered` set from the
  provider's verdict, and are **excluded from the in-app feed** so one status change does
  not appear three times.

### Discovery ([discovery.py](../src/modules/restaurants/discovery.py))

`GET /restaurants` is now the search surface: dish-level matching, filters for city,
cuisine, minimum rating, price band, vegetarian and open-now, four sort orders, and paging.

- **Breaking change:** the endpoint returns a `{items, total, limit, offset}` envelope
  rather than a bare list. Paged results are meaningless without the total. All callers
  were updated.
- Rating and price come from **subquery aggregates**, because you cannot page a set you
  have not finished filtering.
- Sorting by rating puts **unrated restaurants last**, not at the bottom of the scale, and
  breaks ties on review count so 5.0-from-one-review does not outrank 4.8-from-two-hundred.
- Filters only count **available** items, so a sold-out dish cannot keep a restaurant in
  the vegetarian results.
- `is_vegetarian` is non-nullable and defaults false: "unlabelled" has to read as "not
  vegetarian", or the filter misleads a diner.
- Also fixed along the way: the search box had **no accessible name** (a placeholder is not
  one), which the new sort control exposed.

### Reviews, reorder, favourites

- **Reviews:** the author can edit (stamping `updated_at`, so the UI can mark it edited)
  and withdraw; an admin can moderate any; the restaurant owner can reply once, replacing
  rather than threading. An owner deliberately **cannot** edit or delete a review of their
  own business — that is what makes a rating worth reading.
- **Reorder** (`POST /cart/reorder`) refills the cart from a past order, **replacing** its
  contents. Best-effort by design: a delisted or sold-out line is skipped and reported in
  `skipped` rather than failing the whole reorder, and a price change is not a skip — the
  existing price-hash gate already makes the customer confirm the new total.
- **Favourites** are idempotent (a double tap cannot duplicate, enforced by a unique
  constraint rather than a check-then-insert) and scoped to the caller, so un-favouriting
  someone else's saved restaurant returns 404 rather than confirming it exists.

---

## 8. Suggested order of work

**Ship-blocking (do first, roughly a day):** §3.1 and §3.2 are two lines of
`cloudbuild.yaml`. §3.4's two Cloud Scheduler jobs are configuration. §3.3 needs a real
GCS implementation plus the `Thumb` fix. §3.5 rides on whatever scheduler §3.4
establishes.

**Then, cheap and high-value:** add `npm test` to CI (§4.5) and a real readiness check
plus Cloud Run instance/concurrency bounds (§4.6). Reconcile the docs (§6) — that is
writing, not engineering, and it is the difference between a reviewer trusting the repo
and not.

**Then decide, don't drift:** Kafka (§4.2), schema-per-domain (§4.4), and the saga
(§4.3) are all half-committed. Each needs an explicit *build it* or *defer it and amend
the doc*. Leaving them ambiguous is what produced the un-called relay.

**Then hardening:** observability (§4.1) is the biggest single body of remaining work and
the one that determines whether you can operate this in production at all.

**Product scope (§5) is a separate conversation** — it is what to build next, not what is
unfinished.

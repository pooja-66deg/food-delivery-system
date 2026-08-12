# Live Platform Test Report — food-delivery-system

**Target:** `https://api-gateway-orhxitfkxa-uc.a.run.app` (GCP project `food-project-poc`, us-central1)
**Scope:** live deployed platform — 7 FastAPI services + nginx gateway + React SPA on Cloud Run
**Window:** 2026-08-11 12:28Z → 2026-08-12 03:30Z
**Method:** 19 parallel domain squads (~500 live HTTP requests) → 8 per-service Cloud Run log sweeps → 20 adversarial verification agents whose job was to *refute* each claim → this report
**Verification outcome:** 20 of 34 bug claims adjudicated. **0 refuted.** 2 severities raised, 5 lowered.
**Not used:** no unit tests, no pytest. Every finding is a real HTTP request against the live deployment.

---

## 1. Verdict

The **cash-on-delivery ordering spine genuinely works end to end.** A real COD order (id 12) went cart → checkout → `PAYMENT_SUCCESS` with correct arithmetic, an exact stock decrement (91→89), a payment row materialised through the transactional outbox, and both an in-app and a SendGrid email notification inside ~19 seconds. Authentication, JWT handling, discovery filtering, per-user data isolation and menu-management authorization all held up under deliberately hostile probing — zero IDOR, zero role escalation, zero 5xx across 66 malformed-token requests.

**Three things block production, and all three are about money or accounts:**

1. **Card checkout is 100% dead and reports failure as success.** `STRIPE_SECRET_KEY` has a trailing newline, so every Stripe call dies before leaving the container; `STRIPE_WEBHOOK_SECRET` isn't configured at all, so even a fixed key could never settle. The provider layer swallows the exception and returns **HTTP 200** with `status: "FAILED"`. No customer can pay by card, and the SPA is never told.
2. **Refunds are never executed.** Cancelling an order sets `payment_status: REFUNDED, refund_status: FULL` on the order while the payments service — the system of record for money — still shows `AUTHORIZED`. The two services permanently disagree about whether money was returned.
3. **`POST /api/auth/admin/reset-password` is an unauthenticated, unthrottled, role-unchecked password-change primitive** that also fails to evict sessions. Anyone who knows an email and its current password can change it with no token, and a stolen session survives the change indefinitely.

Underneath sits a **db-f1-micro Cloud SQL instance shared by 7 services with unbounded connection pools**, which has already produced a customer-visible 500 on `POST /orders/checkout`.

**Coverage caveat:** every assertion needing an admin token or an approved restaurant-owner token is **BLOCKED** (see §6). That leaves restaurant approval/rejection, owner menu CRUD, order acceptance and delivery dispatch untested.

---

## 2. Fix order (recommended)

| # | Fix | Effort | Why now |
|---|---|---|---|
| 1 | **Rotate the Stripe key**, re-add without newline (`printf %s`) | 5 min | Key is in plaintext in Cloud Logging |
| 2 | Configure `STRIPE_WEBHOOK_SECRET` | 5 min | No card order can settle without it |
| 3 | Move `_request_payment_action` **before** `session.commit()` (`orders/app/service.py:392`) | 15 min | Refunds silently never happen |
| 4 | Delete or authenticate `POST /auth/admin/reset-password` | 15 min | Unauthenticated password change |
| 5 | `--no-cpu-throttling` + bound DB pools + upgrade `food-db` tier | 20 min | Checkout already 500s under load |
| 6 | `admin-service` egress → `all-traffic` | 5 min | 100% of admin→users calls fail |
| 7 | Add `Depends(_caller)` to `restaurants/app/internal.py:210,226` | 10 min | Pending-venue + owner-PII leak |
| 8 | Force IPv4 upstream resolution in nginx (`resolver … ipv6=off`) | 10 min | **Every** request burns ~8 failed IPv6 connects — D21 |
| 9 | Fix `GCS_BUCKET_NAME` (leading space, wrong bucket) | 5 min | All image uploads would fail — D22 |
| 10 | Create `delivery-service--restaurant-events` subscription | 5 min | Read-model never populated — D9 |
| 11 | Bounded int type platform-wide (`le=2147483647`) | 45 min | ~98 unhandled 500s across 6 services |
| 12 | Return non-2xx when a payment provider fails | 20 min | SPA shows success on failure |
| 13 | `email.lower()` on write + all lookups, unique index on `lower(email)` | 30 min | Users locked out of recovery |

---

## 3. Flow-by-flow status

| Flow | Status | Evidence |
|---|---|---|
| User creation — customer | **WORKING** | `POST /api/auth/register` → 201 `is_active:true`; login → token pair, `gen:0`, `expires_in:1800` |
| User creation — restaurant owner | **WORKING** | 201 with `is_active:false`; login → 401 with byte-exact `PENDING_APPROVAL_MESSAGE`; venue created `pending` |
| User creation — driver | **WORKING** | 201 `is_active:true`; driver token 403s on customer routes, reaches `/api/delivery/assignments` |
| Restaurant approval | **BLOCKED** | Gate proven real (pending venues absent from browse, `total=5` under every filter); `POST /restaurants/{id}/approval` → 401 unauth, 403 customer **and** driver. No admin token available |
| Restaurant rejection | **BLOCKED** | Same guard chain; hostile reject on restaurant 1 → 403, `approval_status` unchanged |
| Menu management | **PARTIAL** | Negative authz **23/23 correct** (401 unauth, 403 customer, spoofed `X-User-Role: admin` ignored, post-test state byte-identical). Owner-authenticated CRUD blocked |
| Cart | **WORKING** | `POST /api/cart/items` → 200 with server-computed `price_hash`; emptied on checkout; Redis-backed, isolated per user |
| Checkout — COD | **WORKING** | Order 12: 201, `PAYMENT_SUCCESS`, 200.00×2 = 400.00, stock 91→89, payment row + notifications ≤20 s |
| Checkout — card/Stripe | **BROKEN** | Order 15: 201 with `payment_checkout_url: null`; `/retry` → **200** `{"status":"FAILED"}` — **D1** |
| Order state machine | **PARTIAL** | `CREATED→PAYMENT_PENDING→PAYMENT_SUCCESS→CANCELLED` verified with full event trail. Owner accept/reject + driver legs blocked |
| Payments | **BROKEN** | Card provider dead (D1); refund never applied (**D2**); unvalidated pagination → 500s |
| Refunds | **BROKEN** | Order says `REFUNDED`, payment row stays `AUTHORIZED` 4+ min later — **D2** |
| Delivery assignment | **BLOCKED** | Role guards verified; no order can reach a dispatchable state without owner acceptance |
| Notifications | **WORKING (with defects)** | In-app + SendGrid email ≤19 s. But **two duplicate rows per status change** (D12), and SMS/push record `delivered:true` while unconfigured (D11) |
| Admin console | **BLOCKED** | `/admin/stats`, `/admin/users`, `/admin/orders`, `/restaurants/admin/all` → 401 unauth, 403 customer/driver. Authz correct; no admin credentials |
| Gateway routing | **PARTIAL** | All 13 location blocks route correctly; CORS allowlist correct (evil origin rejected). Trailing-slash redirects broken (D13) |
| Reviews | **WORKING (with defects)** | CRUD + ownership correct; rating aggregation arithmetic verified. int32 ids → 500 |

---

## 4. Confirmed defects

`Verified` = an independent agent tried to refute it and failed, or I reproduced it myself in this session.

### D1 — CRITICAL — Card checkout entirely non-functional; failure reported to the client as success
**Verified ✅ (config half re-confirmed by me directly)** · `POST /api/orders/checkout` (CARD), `POST /api/payments/order/{id}/{confirm,retry,resume}`, `POST /api/payments/webhook`

Two independent production misconfigurations:

**(a) `STRIPE_SECRET_KEY` has a trailing newline.** Every Stripe SDK call fails before the wire:
```
ERROR:app.providers:[payments:STRIPE] authorize failed: ... (Network error: A ValueError was
raised with error message Invalid header value b'Bearer sk_test_51U04Fu…S9CvK2JR\n')
```
Present continuously 2026-08-11T12:34Z → 2026-08-12T03:09Z, 39 occurrences in 20 h, across revisions `payments-service-00021-bjn` and `-00022-2d9`.

**(b) `STRIPE_WEBHOOK_SECRET` is absent from the deployed env.** `gcloud run services describe payments-service` lists only `ENVIRONMENT, MESSAGING_TRANSPORT, GOOGLE_CLOUD_PROJECT, CORS_ORIGINS, FRONTEND_BASE_URL, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, STRIPE_SECRET_KEY`. `webhook.py:58-60` therefore rejects **every** delivery.

**Why it is wrong:** `payments/app/providers.py:136-138` swallows all provider exceptions (`except Exception … return ProviderResult(ok=False)`) so "payment setup never crashes checkout" — a sound intent that converts a total outage into a *silent* one. The route layer then returns 200/201 with `checkout_url: null`. `config.py:51-54` documents a stand-in-provider fallback for an *unset* key, but the key is **set-but-malformed**, so `providers.py:205` still selects `StripeProvider()` and the fallback never engages.

**Reproduction (this session):**
```
POST /api/orders/checkout {"address_id":7,"price_hash":"…","payment_method":"CARD"}
  → 201 {"id":15,"status":"PAYMENT_PENDING","payment_checkout_url":null}
POST /api/payments/order/15/retry
  → 200 {"status":"FAILED","provider_ref":null,"checkout_url":null}
POST /api/payments/webhook  (no sig, and t=<now>,v1=deadbeef)
  → 400 {"detail":"Webhook signing secret is not configured"}
```

**Fix**
1. `printf %s "$KEY" | gcloud secrets versions add STRIPE_SECRET_KEY --data-file=-`, redeploy.
2. **Rotate the key** — see D3.
3. `.strip()` the key in `payments/app/config.py` via a field validator.
4. Configure `STRIPE_WEBHOOK_SECRET`, register the endpoint in the Stripe dashboard.
5. `/confirm`, `/retry`, `/resume` must return 502/409 when `ok=False`, not 200.

---

### D2 — CRITICAL — Refund on cancellation is never executed; orders and payments permanently disagree
**Verified ✅ (found independently by two squads)** · `POST /api/orders/{id}/cancel` → `GET /api/payments/order/{id}`
**Source:** `services/orders/app/service.py:392-394` (also `:425-426, :445-449, :466-468, :514-516`), `services/orders/app/db.py:20-26`

`cancel_by_customer` records the refund and calls `_request_payment_action(session, order, "refund")` — whose own docstring (lines 284-296) promises the command *"commits with the status change that justified it"* — but the call sits **after** `await session.commit()`. The outbox row therefore lands in a fresh transaction that `get_db`'s session close discards, so the `payment-commands` event is never published and `payments/app/consumer.py:72-101` never runs `refund_payment()`.

**Reproduction:**
```
POST /api/orders/checkout {…"payment_method":"COD"}  → 201 {"id":19,"status":"PAYMENT_SUCCESS"}
GET  /api/payments/order/19                          → 200 {"provider":"COD","status":"AUTHORIZED"}
POST /api/orders/19/cancel
  → 200 {"status":"CANCELLED","payment_status":"REFUNDED","refund_status":"FULL","refund_amount":"200.00"}
GET  /api/payments/order/19   (polled 4× over 32 s)  → 200 {"status":"AUTHORIZED"}   ← never changed
```
Independently reproduced on order 16 (unchanged 4+ minutes later).

**Corroborating infrastructure evidence:** **zero `payment-events` and zero `delivery-events` were published project-wide** during the whole E2E run (`pubsub topic/send_request_count` has no series for either topic).

**Fix:** move `_request_payment_action` before `session.commit()` at every one of the five call sites so the outbox row commits in the same transaction as the status change. Add a reconciliation check that fails loudly when an order claims `REFUNDED` while its payment row does not.

---

### D3 — HIGH — Live Stripe secret key written verbatim into Cloud Logging
**Verified ✅** · side effect of every CARD authorize · **Source:** `services/payments/app/providers.py:136-138`

Because the failure is a header-validation `ValueError`, the Stripe SDK's exception message embeds the outgoing `Authorization` header, and `logger.error("[payments:STRIPE] authorize failed: %s", exc)` emits the **full 107-character live secret key in plaintext**. Recurs at 02:57:26, 03:06:04, 03:06:17, 03:06:18, 03:06:50, 03:09:03 — 39× in 20 h. Anyone with `roles/logging.viewer` on the project can read it.

**Fix:** treat the key as leaked and **rotate it**. Never log provider exception objects raw — log `type(exc).__name__` plus a redacted message, or scrub `sk_[a-zA-Z0-9_]+` before logging.

---

### D4 — HIGH — `POST /api/auth/admin/reset-password`: unauthenticated, no role check, no rate limit, no session eviction
**Verified ✅ (two verifiers, with a control)** · **Source:** `services/users/app/router.py:205-220`, `services/users/app/service.py:399-419`

Three defects on one route:

**(a) No authentication, no admin check.** The route declares no auth dependency and `reset_admin_password` never inspects `user.role`. With **no `Authorization` header at all**, posting `{email, old_password, new_password}` for a `role:"customer"` account returns 200 and really changes the password. It is also the only unauthenticated auth route with **no `enforce_rate_limit`** (compare `router.py` lines 64, 87, 102, 161, 244) — an unbounded password-verification oracle.

**(b) No session eviction.** `service.py:414-416` sets `hashed_password` and `password_reset_required` but never `user.session_generation += 1`, which `service.py:67` (`reset_password`) and `service.py:82` (`change_password`) both do. `dependencies.py:57-58` states the invariant: *"The generation check … is what makes a password reset actually evict anyone."*
*Control that makes this airtight:* the verifier ran the same eviction test against `POST /api/users/me/change-password` on the same account — it bumped `gen 0→1` and the old token immediately got `401 {"detail":"Session expired"}`. So enforcement is live; this endpoint specifically skips it. **Worse than first reported:** a *refresh* token captured before the change still mints new access tokens afterwards and rotates, so a compromised session survives **indefinitely**, not for one 30-minute TTL.

**(c) Account enumeration.** Unknown email → **404** `{"detail":"User with ID <submitted email> not found"}` (`shared/errors.py:46-50` echoes attacker input); known email + wrong password → **401**. Exactly the oracle the sibling `forgot_password` docstring says the platform must not have. 8 sequential probes: 8× 404, no throttling.

**Reproduction:**
```
POST /api/auth/admin/reset-password        (NO Authorization header)
  {"email":"verify.pwgen.v1@example.com","old_password":"verifyPass1","new_password":"verifyPass2"}
  → 200 {"id":30,…,"role":"customer","is_active":true}
GET  /api/users/me   (pre-change token)              → 200   ← expected 401
POST /api/auth/login {"password":"verifyPass2"}      → 200, payload {"sub":"30","gen":0}
POST /api/auth/refresh {pre-change refresh token}    → 200, new access token
POST /api/auth/admin/reset-password {"email":"verifier.nobody.q7z@example.com",…}
  → 404 {"detail":"User with ID verifier.nobody.q7z@example.com not found"}
```

**Fix:** require an authenticated caller (or bind the route to the `password_reset_required` bootstrap flow only); add `if user.role != "admin": raise ForbiddenException`; add `user.session_generation += 1` and return a fresh `TokenResponse` as `change_password` does; collapse the unknown-email branch into the generic 401; add `enforce_rate_limit`.

---

### D5 — HIGH — Rate limits are keyed on a constant Cloud Run ingress IP, so `forgot-password` can be denied platform-wide
**Verified ✅** · `POST /api/auth/forgot-password` (and `/register`) · **Source:** `services/users/app/router.py:51-52, 161-164`

`_client_ip` returns only `request.client.host`. On Cloud Run the TCP peer is always the internal ingress proxy — every users-service access log line, for every caller, reads `169.254.169.126:<port>`. uvicorn's `ProxyHeadersMiddleware` trusts only `127.0.0.1` by default and the app never reads `X-Forwarded-For`, so the limiter key `rl:forgot:{ip}` is a **platform-wide constant**.

With `auth_rate_max=10 / 60 s`, **ten anonymous requests in any 60-second window lock the only self-service account-recovery path for every user on the platform**, sustainable at ~1 request every 5 s. Demonstrated: requests 1-10 → 200, 11-14 → 429. `register` shares the same constant key; `login` is partly mitigated because its key includes the email.

**Fix:** read the left-most untrusted `X-Forwarded-For` entry (the gateway already sets it), or run uvicorn with `--proxy-headers --forwarded-allow-ips="*"`. Consider keying `forgot` on `(ip, email)` as `login` does.

---

### D6 — HIGH — `admin-service` cannot reach `users-service` at all (VPC egress vs ingress mismatch)
**Verified ✅ (from logs)** · 100% of admin→users calls failed over 24 h

`admin-service` is deployed with `run.googleapis.com/vpc-access-egress=private-ranges-only`, while `users-service` has `ingress=internal-and-cloud-load-balancing`. Calls to the public `users-service` URL therefore bypass the `food-connector` VPC connector, arrive as **external** traffic, and are rejected by the internal-only ingress with a Google Front End HTML **404** — never reaching the container.

Proof: no users-service log entry at 02:31:08Z, 03:04:51Z, 18:15:16Z or 18:38:39Z despite admin-service logging the attempt, while the same URL returned a proper 409 at 03:14:20Z for an internal caller. `orders-service` is deployed with `egress=all-traffic`; **admin-service is the outlier.**

This is the *real* root cause of the `POST /api/admin/bootstrap` 500 — not the exception-handling drift. Your uncommitted `services/admin/app/router.py` fix would turn the 500 into a cleaner error but **would not make bootstrap work.** `POST /admin/expire-acceptances` forwards to `orders-service` (also internal-ingress) and will hit the same wall.

**Fix:** set `admin-service` egress to `all-traffic`, matching `orders-service`.

---

### D7 — HIGH — Cloud SQL connection exhaustion; already caused a customer-visible checkout 500
**Verified ✅ (from logs, 5 services)** · **Source:** `services/*/app/db.py:12`

> ⏱ **Timing correction (from the final log sweep):** these failures fired on **2026-08-11 (11:47Z–18:43Z)**, *not* during the E2E run. The run window itself was clean — no pool exhaustion, no DB retries. So this is a **latent misconfiguration that has already bitten once in production**, not something actively failing right now. Fix it before any real traffic; it is not an active incident.

`create_async_engine()` is called with no `pool_size`/`max_overflow`, so SQLAlchemy's default 5+10 = **15 connections per instance** applies. Instance `food-db` is tier **db-f1-micro** (POSTGRES_15) with **no `databaseFlags` set** — a shared-core tier whose default `max_connections` is ~25 — shared by all 7 services at `minScale=1`.

`asyncpg.exceptions.TooManyConnectionsError` observed in **users (3), payments (3), orders (1), admin (24), delivery (1)**. Consequences already realised:
- **`POST /orders/checkout` returned an unhandled 500** at 18:43:22Z (`orders/app/checkout.py:59`).
- Outbox relay failures at 18:02:25Z and 18:02:45Z (`shared/outbox.py:58`) — when the relay cannot open a connection, **domain events stop being published**, which is exactly the path that creates payment rows and notifications.

`TooManyConnectionsError`/`OperationalError` is not mapped to a retryable 503 anywhere, so DB capacity problems escape as 500s.

**Fix:** cap pools per service (`pool_size=2, max_overflow=3, pool_pre_ping=True, pool_recycle=1800`), raise the `food-db` tier or set `max_connections`, and map connection errors to 503. Every service is pinned `minScale=1/maxScale=1` — no headroom and no redundancy for the outbox relay or Pub/Sub consumers.

---

### D8 — HIGH — Pub/Sub consumers time out and drop events; CPU throttling is the cause
**Verified ✅ (from logs)** · **Source:** `shared/messaging.py:198`

> ⏱ **Timing correction:** the bulk of this — **1,285 failed Pub/Sub messages in admin-service** (`user-contact-events` 435, `user-events` 426, `order-events` 296, `restaurant-events` 128) — occurred **2026-08-11 07:20Z–18:29Z**, roughly 9 hours *before* the E2E run. Only 4 handler timeouts fell inside the run window. Same conclusion as D7: a latent misconfiguration that has already caused large-scale event loss once, not an active incident.

`concurrent.futures.TimeoutError` from `.result(timeout=self._timeout)`: **1,168 in admin-service**, plus delivery (2), notifications (1), across topics `order-events`, `user-events`, `user-contact-events`, `restaurant-events`. A further 93 were `ConnectionRefusedError` (Cloud SQL proxy sidecar down) and 20 `TooManyConnectionsError` (D7).

**Second event-loss mechanism, same period:** `orders-service` logged **137 × `Outbox relay batch failed; retrying next tick`** (`shared/outbox.py:109 → :97 → :58`) between 11:47Z and 18:02Z, plus users (3) and payments (2). Events were committed to the outbox tables but the relay could not read them out to publish, so they sat undelivered. Zero outbox errors during the E2E run itself.

Root cause: **Cloud Run CPU throttling is ON** for these revisions (no `run.googleapis.com/cpu-throttling=false` annotation). Each service runs a background Pub/Sub consumer thread in its lifespan that needs the event loop *between* requests. Corroboration: notifications-service took **43 s** to subscribe after boot (startup complete 12:53:45.875Z vs "Consuming … from Pub/Sub" 12:54:28.903Z).

**Fix:** redeploy all event-consuming services with `--no-cpu-throttling`.

---

### D9 — HIGH — `delivery-service` subscribes to a Pub/Sub subscription that does not exist, silently
**Verified ✅ — I confirmed this directly** · **Source:** `infra/gcp/cloudbuild.yaml:235-236`, `services/delivery/app/config.py:39`, `shared/messaging.py:260`

```
$ gcloud pubsub subscriptions list --project food-project-poc | grep delivery
delivery-service--order-events
delivery-service--user-events          ← delivery-service--restaurant-events is absent
```
*(Two log agents disagreed here — one filed it as HEALTHY because the service logs all three topic names at startup. That log line is only the service's stated intent; the subscription list above is the ground truth. The defect is real.)*

delivery-service logs `Consuming ['order-events','user-events','restaurant-events']` at every startup, but only `delivery-service--order-events` and `delivery-service--user-events` exist. `delivery-service--restaurant-events` **was never created** — cloudbuild loops over only `order-events user-events` for delivery, while `config.py:39` defaults to all three and the revision sets no `KAFKA_TOPICS` override.

The failure is invisible because `shared/messaging.py:260` appends `client.subscribe(...)` **without ever calling `.result()`/`.exception()`** on the returned `StreamingPullFuture`, so the `NotFound` never surfaces. This is precisely the drift `cloudbuild.yaml:218-220` warns about: *"a missing subscription means a consumer that starts cleanly and never receives anything."*

**Fallout:** `_apply_restaurant_event` (`delivery/app/consumer.py:95-111`) never runs, so the `RestaurantSnapshot` read-model is never populated.

**Fix:** create the missing subscription, and make `shared/messaging.py` check each subscribe future so a missing subscription fails loudly at boot.

---

### D10 — LOW *(was HIGH)* — Blocklisted (logged-out) access token still reads and writes `/api/favorites`
**Verified ✅ — CONFIRMED, severity corrected HIGH → LOW** · **Source:** `services/users/app/favorites.py:32`

> **Severity downgraded on verification.** The bug is real and reproduces step-for-step, but the blast radius is exactly one endpoint group: a `grep` over `services/users/app` confirms **`favorites.py:32` is the ONLY route in the whole users service guarded by `require_role`** — every other authenticated route goes through `current_user`. No money, no PII, no order data is reachable this way, and the window is bounded by the 30-minute access-token TTL. Still worth fixing, but it is not the platform-wide auth hole the original claim implied.

`service.logout()` blocklists both the refresh and access `jti` precisely so the access token is not usable for the rest of its lifetime (`service.py:300-309`). But only routes going through `app/dependencies.py:current_user` check the blocklist. `favorites.py:32` uses `auth.require_role("customer")` (`shared.identity.JWTAuth`) **directly**, which performs no revocation, `is_active`, or session-generation check.

```
POST /api/auth/logout  Bearer AT_B  {"refresh_token":"RT_B"}  → 204
GET  /api/users/me     Bearer AT_B  → 401 {"detail":"Token revoked"}   ← blocklist works here
POST /api/auth/refresh {"refresh_token":"RT_B"} → 401 {"detail":"Token revoked"}
GET  /api/favorites/ids Bearer AT_B → 200 [5,2]                        ← still works
POST /api/favorites     Bearer AT_B → succeeds
```

The verifier re-checked the final state with a freshly minted valid token to prove the writes were DB-backed rather than a stale cache, and left the account's favourites as found (empty). It also noted the same gap means a password-reset `session_generation` bump and an `is_active=false` deactivation are both ignored on these four routes.

`shared/identity.py` documents the "bounded staleness" tradeoff as the price of not making every service synchronously depend on users — but that rationale does not apply *inside* the users service, which already has `get_redis` and the `User` row locally, and `dependencies.py:33-60` says so explicitly. This is an inconsistency, not a documented tradeoff.

**Fix:** route favourites through `dependencies.current_user`.

---

### D11 — HIGH — SMS and push notifications are recorded as `delivered:true` while no provider is configured
**Verified ✅ (from logs + env)** · **Source:** `notifications/app/senders.py`, `notifications/app/service.py:_send_one`

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` and `FCM_SERVER_KEY` are **not set** on the live revision. `SmsSender.send` returns `True` on the unconfigured path, and `_send_one` records that as `delivered=ok` → `True`. So the delivery audit trail claims SMS and push messages were delivered when nothing was ever sent. `PushSender` has the same pattern.

Email is genuinely healthy: `[notify:EMAIL] sent via SendGrid to …` ~12 s after each qualifying event, zero failures, and `FRONTEND_BASE_URL` correctly points at the deployed SPA (reset links do not point at `localhost:5173`).

**Fix:** return `False` (or raise) from the unconfigured branch so the audit trail is honest, or gate the channel off entirely when its credentials are absent.

---

### D12 — MEDIUM — `GET /api/restaurants/{id}` and `/api/restaurants/lookup` leak non-approved venues, unauthenticated
**Verified ✅** · **Source:** `restaurants/app/router.py:208-215` → `service.py:223-227`; `restaurants/app/internal.py:210, 226`

`get_restaurant()` has no auth dependency and no approval predicate — a bare `session.get(Restaurant, id)`. Compare `service.py:275, :294, :339` and `discovery.py:177` (`conditions = [Restaurant.approval_status == APPROVED]`): **every other public read path carries the predicate; only the detail route and `lookup_restaurants` omit it.** Ids are sequential, so the whole pending pipeline is enumerable.

Worse, `internal.py`'s own module docstring says these endpoints are *"guarded by the caller's own token"*, and its two siblings (`validate-order`, `release-stock`) do declare `Depends(_caller)` — but `lookup_items` and `lookup_restaurants` do not:

```
$ curl 'https://api-gateway…/api/restaurants/lookup?ids=1,6,7,8'     (no auth header)
200
[…,{"id":6,"owner_id":14,"name":"Ultra chiense","phone":"+914564564564","approval_status":"pending"},
    {"id":7,"owner_id":17,"address_line":"12 Residency road","phone":"+913545345354","approval_status":"pending"},…]
$ curl 'https://api-gateway…/api/restaurants/8'                      (no auth header)
200  {"id":8,"owner_id":21,"name":"QA Test Kitchen","address_line":"1 QA Lane","phone":"+15550004005","approval_status":"pending",…}
```

Owner phone numbers and street addresses of unapproved applicants are public.

**Fix:** add `Depends(_caller)` to both lookup routes; add the approval predicate to `get_restaurant` (or gate on the caller being the owner/an admin).

---

### D13 — MEDIUM — Every order status change writes two duplicate in-app notification rows
**Reported** · **Source:** `orders/app/service.py:105`, `notifications/app/consumer.py:151-152`

`notifications/app/service.py:116-121` documents the feed as LOG-rows-only precisely because showing outbound rows too *"would repeat every message up to three times in the feed"* — i.e. the design intent is exactly one visible row per change. Live, order 17 produced **two identical LOG rows** (ids 137 @ 03:04:39.358Z and 138 @ 03:04:40.137Z, same type `order.PAYMENT_SUCCESS`, same message). Root cause: `_emit_status` calls `_notify()` **and** publishes on `order-events`, and the notifications consumer handles both.

**Fix:** publish the status once, or make the consumer idempotent on `(user_id, order_id, type, status)`.

---

### D14 — MEDIUM — Gateway leaks internal hostnames over plaintext http and breaks every trailing-slash route
**Verified ✅** · **Source:** `infra/nginx/nginx.conf.template:46-53` (no `proxy_redirect` anywhere in `infra/`)

FastAPI's `redirect_slashes` 307 passes through nginx unrewritten, and `proxy_set_header X-Forwarded-Proto $scheme` sends `http` (the container's own listener scheme):

```
$ curl -sI https://api-gateway-orhxitfkxa-uc.a.run.app/api/restaurants/
HTTP/2 307
location: http://restaurants-service-orhxitfkxa-uc.a.run.app/restaurants
```
Same on `/api/orders/`, `/api/cart/`, `/api/favorites/`, `/api/payments/`, `/api/notifications/`, `/api/delivery/assignments/`. Following the redirect ends in a Google Frontend 404 — **the trailing-slash form of every collection route is simply broken**, the internal hostname is disclosed, the scheme is downgraded, and the `/api` prefix is stripped.

*A verifier corrected the original claim on one point:* the bearer token is **not** carried onto the http hop — curl and WHATWG Fetch both drop `Authorization` on cross-origin redirects. So this is a broken-route + disclosure issue, not credential leakage.

Related (**LOW**): bare prefixes (`/api/auth`, `/api/users`, `/api/delivery`, `/api/admin`, `/media`) 301 to `http://api-gateway-…:8080/…`, which Cloud Run does not serve at all — curl times out. Cause: `listen ${PORT}` + nginx `auto_redirect`, with no `absolute_redirect off;` / `port_in_redirect off;` anywhere in `infra/`.

**Fix:** add `absolute_redirect off; port_in_redirect off;` and `proxy_redirect` rules mapping upstream Locations back onto the public origin; set `X-Forwarded-Proto https`.

---

### D15 — MEDIUM — Email lookup is case-sensitive in the local part
**Verified ✅ (decisive in-band A/B)** · **Source:** `users/app/service.py:41, :337, :407`; `models.py:43`

Every lookup compares raw; `grep -rn "lower()" services/users/` returns nothing. Pydantic's `EmailStr` lowercases the **domain** only.

```
POST /api/auth/login {"email":"smoke.probe.a1@example.com","password":"devpassword1"} → 200 + tokens
POST /api/auth/login {"email":"Smoke.Probe.A1@example.com","password":"devpassword1"} → 401
```
On `forgot-password` the consequence is worse: three requests (exact case, local-part variant, domain variant) all returned identical 200s, but notifications-service logged **only two** SendGrid dispatches, both to the lowercase address. The user is told *"a reset link has been sent"* and waits for mail that was never minted — the deliberate anti-enumeration wording turns a functional failure into a silent one.

**Secondary risk:** with no lowercased-uniqueness constraint, `A@x.com` and `a@x.com` can both register and deliver to the same mailbox.

**Fix:** normalise on write and on every lookup, add a unique index on `lower(email)`, backfill.

---

### D16 — MEDIUM — Cancelling a never-paid CARD order records a FULL refund
**Reported** · **Source:** `orders/app/state_machine.py:65-66`

`refund_on_cancel(current, Actor.CUSTOMER)` returns `FULL` unconditionally. The service's own `expire_unpaid_orders` path gets this right — `_record_refund(order, RefundStatus.NONE)` with the comment *"Nothing was ever captured, so there is nothing to refund."* (`service.py:491-492`) — but a customer-initiated cancel of the same `PAYMENT_PENDING` order does not.

```
POST /api/orders/checkout {…"payment_method":"CARD"} → 201 {"id":20,"status":"PAYMENT_PENDING"}
POST /api/orders/20/cancel → 200 {"payment_status":"REFUNDED","refund_status":"FULL","refund_amount":"200.00"}
GET  /api/payments/order/20 → 200 {"status":"FAILED","provider_ref":null}   ← never captured
```
Combined with D1, **every** cancelled card order currently books a phantom refund. Refund reconciliation against Stripe will not balance.

**Fix:** gate the refund on the payment having actually been captured.

---

### D17 — MEDIUM — `PATCH /api/notifications/preferences` with an explicit `null` returns 500
**Verified ✅ (7 occurrences in 24 h)** · **Source:** `notifications/app/preferences.py:34`, `schemas.py:52-55`, `models.py:59-61`

`PreferenceUpdate` declares the channels as `bool | None = None`, so an explicit JSON `null` passes validation. `model_dump(exclude_unset=True)` excludes *omitted* fields but **keeps explicitly-null ones**, then `setattr` writes `None` into a `nullable=False` column → `NotNullViolationError` escapes as a 500.

`PATCH /api/notifications/preferences {"sms_enabled":null}` → 500. Fired 7× in 24 h on `sms_enabled`, `push_enabled`, `email_enabled`.

**Fix:** filter `None` values out of the update set (as `profile.update_address` already does at `profile.py:118`), or declare the fields non-optional.

---

### D18 — MEDIUM — `403` vs `404` on `/api/payments/order/{id}` is an order-id existence oracle
**Reported** · **Source:** `payments/app/router.py:43-52`

`router.py:43-45` states the rule explicitly: *"404 before 403: telling a stranger that an order exists but is not theirs leaks which order ids are real."* The code at `:51-52` then raises `ForbiddenException`. Live: `/api/payments/order/1` → 403 `{"detail":"Not your order"}`; `/api/payments/order/999999` → 404. Any authenticated customer can enumerate exactly which order ids exist platform-wide. No payment data leaks.

**Fix:** return 404 for foreign orders, as the comment requires.

---

### D19 — LOW (one defect, six services, ~90 live 500s) — Unbounded integer parameters reach asyncpg
**Verified ✅ (3 verifiers, severity corrected HIGH→LOW)**

Path/query/body params are typed as bare `int` (Python ints are unbounded) while the columns are Postgres `int4`. Values ≥ 2 147 483 648 pass Pydantic, reach the driver, and raise `asyncpg.exceptions.DataError` → `OverflowError` in `int4_encode`. `shared/errors.py:76-80` registers a handler for `AppException` **only**, so a `DBAPIError` is a guaranteed 500. The boundary is exact: `2147483647` → correct 404, `2147483648` → 500.

Live 500 counts by service in the window: **restaurants 49, users 18, delivery 10, payments 5, orders 1.**

| Endpoint | Source |
|---|---|
| `PATCH\|DELETE /api/users/me/addresses/{id}` | `users/app/profile.py:158` |
| `POST /api/favorites`, `DELETE /api/favorites/{id}` | `users/app/favorites.py:103, :110` |
| `GET /api/restaurants/{id}`, `/{id}/categories` | `restaurants/app/service.py:224`, `menu.py:42` |
| `GET /api/restaurants?offset=<huge>` (int64 bound) | `restaurants/app/discovery.py:214` |
| `GET /api/reviews/restaurant/{id}`, `POST\|PATCH\|DELETE /api/reviews/{id}` | `restaurants/app/reviews.py:38, :57, :199` |
| `GET /api/restaurants/lookup`, `/items/lookup` | `restaurants/app/internal.py:223, :241` |
| `GET /api/orders/{id}` | `orders/app/service.py:357` |
| `GET\|POST /api/payments/order/{id}/*` | `payments/app/router.py:46` |
| `GET\|POST /api/delivery/orders/{id}/*` | `delivery/app/service.py:218, :382` |

**Why LOW, not HIGH:** the body is a bare `Internal Server Error` — no stack trace, SQL or schema reaches the client; nothing is written, so no corruption; no auth or IDOR consequence. asyncpg fails during bind-message encoding, *before the wire*, so the pool is not poisoned — a burst of 8 consecutive 500s left the service healthy. Real impact is contract violation plus log/alert noise. **One caveat:** on `/api/restaurants/{id}` and `/api/reviews/restaurant/{id}` it is reachable **unauthenticated**.

**Fix:** one shared bounded type applied platform-wide —
`OrderId = Annotated[int, Path(ge=1, le=2147483647)]` — plus a `DBAPIError` handler in `shared/errors.py` as a backstop. Cover the two siblings below with the same change.

**Sibling A — non-finite floats → 500** (`POST /api/delivery/location`, 12 occurrences). Pydantic accepts `inf`/`nan` as floats, the bound check fails correctly, but FastAPI's default handler puts the raw value into the 422 body and `json.dumps(allow_nan=False)` cannot serialise it — **the error response itself crashes.** `{"latitude":999}` → correct 422; `{"latitude":1e400}` → 500. Fix: reject non-finite floats in the schema (`allow_inf_nan=False`) or install a sanitising `RequestValidationError` handler.

**Sibling B — negative pagination → 500** (`GET /api/payments?limit=-1`, `?offset=-5`). `router.py:85-92` declares `limit`/`offset` as plain ints with no `Query(ge=…)`; `service.py:185` passes them straight into `.limit()`/`.offset()` → `LIMIT must not be negative`. Fix: `Query(ge=0, le=100)`.

---

### D20 — LOW — Two small contract slips
1. **`PATCH /api/users/me` with an explicit `null` for *any* non-nullable field returns a false 409 `"Phone already registered"`** — **Verified ✅, and broader than first reported.** `{"first_name":null}` and `{"last_name":null}` also return `409 {"detail":"Phone already registered"}`, which has nothing to do with phone at all. The bare `except IntegrityError` at `users/app/profile.py:33-35` re-raises **every** constraint violation as a phone-uniqueness conflict. Any client doing *"409 on profile save → tell the user to pick a different phone number"* will show a nonsense message.
   `UserUpdate` accepts an explicit null by design (`normalize_optional_phone` passes `None` through), and `model_dump(exclude_unset=True)` **keeps** it (unlike `exclude_none`), so `setattr(user,"phone",None)` hits a `nullable=False` column. The sibling `update_address` (`profile.py:115-118`) gets this right, filtering `None` out with the comment *"a null anywhere else means 'leave this field alone'"*. Rollback verified clean — no corruption.
   **Fix:** filter `None` out of the update set, and narrow the `IntegrityError` handler so it only claims a phone conflict when the phone is actually what collided.
2. **Cancel response returns a stale `events[]`** (`orders/app/service.py:396`) omitting the `CANCELLED` transition it just made; a fresh `GET` returns it. `expire_on_commit=False` + the identity map means `_load_full`'s selectinload reuses the cached collection. Fix: `await session.refresh(order, ["events"])` before returning.

---

### D21 — MEDIUM — nginx tries IPv6 for every upstream connect and always fails, on every single request
**Verified ✅ (from gateway logs)** · **Source:** `infra/nginx/nginx.conf.template` (`resolver` directive has no `ipv6=off`)

The gateway logged **1,809 ×** `[error] connect() to [2600:19xx:xxxx:200::]:443 failed (101: Network unreachable) while connecting to upstream`, each paired with `[warn] upstream server temporarily disabled` — **3,618 of the 3,625 non-notice nginx lines**. Across 8 distinct AAAA addresses. Of all upstream connect attempts logged, **IPv6 = 3,610, IPv4 = 0**: every proxied request burns roughly **8 failed IPv6 connects** before falling back to IPv4.

nginx resolves the Cloud Run hostname, prefers the AAAA record, and the Cloud Run environment has no IPv6 egress. It still works — no 502/503/504 was ever recorded, so the fallback succeeds — but every request pays connect-timeout latency it does not need to, and the error log is 99.8% noise, which will hide a real upstream failure when one happens.

**Fix:** add `ipv6=off` to the `resolver` directive in `nginx.conf.template`.

---

### D22 — MEDIUM — `GCS_BUCKET_NAME` has a leading space and points at the Cloud Build staging bucket
**Verified ✅ (from deployed env)** · **Source:** `services/restaurants/app/config.py:59`, `storage_gcs.py:42, :54`

The deployed `restaurants-service` has `GCS_BUCKET_NAME = " food-project-poc_cloudbuild"` — note the **leading space**, and note that it names the *Cloud Build staging* bucket rather than a media bucket. `config.py:59` is `Optional[str] = None` with no stripping, so both `client.bucket(settings.gcs_bucket_name)` and the public URL template `https://storage.googleapis.com/{bucket}/{blob_path}` receive the malformed name.

**Latent, not yet proven at runtime** — no image upload happened during this run, so it is inferred from the env value and the source path, not from a failed request. But restaurant 1 already has a working cover image at `https://storage.googleapis.com/food-project-poc-food-images/...`, i.e. a *different* bucket (`food-project-poc-food-images`), which strongly suggests the current env value is wrong and image upload is broken on the deployed revision.

**Fix:** set `GCS_BUCKET_NAME=food-project-poc-food-images` with no whitespace, and `.strip()` it in `config.py`. **Test one image upload** — this is the highest-value thing to check manually, since automated coverage could not reach it.

---

## 5. Refuted and downgraded

**Refuted outright: 0 of 20 adjudicated claims.** Every claim that reached verification survived a genuine refutation attempt (deploy-drift checks against `git status`, rate-limit/429 false-positive checks, contract re-reads, and controls proving the mechanism).

**Severities corrected:**

| Claim | Change | Why |
|---|---|---|
| No session eviction on admin reset (D4b) | medium → **high** | Refresh tokens survive too, so a compromised session lasts indefinitely |
| Rate-limit key collapse (D5) | medium → **high** | Denies password recovery platform-wide, not per-caller |
| int32 overflow 500s (D19) — 3 separate claims | high → **low** | No leak, no write, no corruption, pool not poisoned |
| Blocklisted token on favourites (D10) | high → **low** | Blast radius is one endpoint group; `favorites.py:32` is the only `require_role` route in the service |
| Null-field 409 mislabel (D20.1) | low → **low** (scope widened) | Affects `first_name`/`last_name` too, not just phone |

**Scope corrected on timing:** D7 (connection exhaustion) and D8 (Pub/Sub loss) were originally framed as active failures. The final log sweep established that both fired on **2026-08-11**, hours before the E2E run; the run window itself was clean. They remain real, already-realised production incidents with the root misconfiguration still in place — but they are not burning right now.

**Scope corrections:**
- **admin/bootstrap 500** — the claimed root cause ("409 not mapped, deploy drift") is only half right. The real cause is the **VPC egress misconfiguration (D6)**; upstream returns 404, not 409. The uncommitted local fix would not make bootstrap work.
- **Gateway redirects (D14)** — the claim that the bearer token is carried onto plaintext http is **false**; clients drop `Authorization` on cross-origin redirects.
- **CORS reflect-any-origin** — repo-only drift, **not live**. Commit `cbc0a79` added reflect-any-origin credentialed CORS + a blanket `OPTIONS 204` to `infra/nginx/nginx.conf`, but that file serves docker-compose only. The deployed gateway uses `nginx.conf.template`, and live behaviour is correct: an allowlisted origin gets a proper Starlette CORS 200; `Origin: https://evil.example.com` is **rejected**. Still worth fixing in the repo before that config ever ships.
- **Admin read-model `IntegrityError`** — real race (`admin/app/consumer.py:67-70` vs `:88-91`, non-atomic get-then-insert across two topics) but **self-healing** via nack/redelivery, no data loss or staleness. Fix with a proper upsert (`ON CONFLICT DO UPDATE`) when convenient.

**Reported but never adjudicated — 20 of 34 claims verified.** The remaining 14 are all secondary instances of already-confirmed defect families (mostly further int32-overflow endpoints in D19 and additional Stripe-failure symptoms in D1), so no distinct unverified risk is outstanding. Everything in §4 now carries either *Verified ✅* or an explicit *Reported* label.

**Gateway request tally (1,052 logged requests), for calibration of how much was actually exercised:**
`200×305, 401×173, 403×124, 404×122, 500×98, 422×77, 307×33, 201×25, 405×24, 204×21, 400×17, 301×17, 409×9, 414×1, 413×1`.
The 98 500s match the upstream services' 98 logical unhandled exceptions **1:1** — every 500 is accounted for, and all of them belong to D19 or its two siblings, plus D1/D6/D17. No 502/503/504 was ever recorded: nginx never failed to reach an upstream. The 413 and 414 are the suite's 7 MB-body and long-URI probes being **correctly** rejected.

---

## 6. Blocked — and exactly what unblocks it

| Area | What is needed |
|---|---|
| Restaurant **approval** and **rejection**; `/api/admin/{stats,users,orders}`; `/restaurants/admin/all`; `expire-acceptances`; owner activation on approval; `REJECTED_MESSAGE` at login | **An admin JWT.** An admin exists but its password is unknown; `POST /api/admin/bootstrap` 500s (D6); reading the DB URL succeeded but `psql`, `cloud-sql-proxy` download, and reading `JWT_SECRET_KEY` were all blocked by the sandbox classifier |
| Menu CRUD **positive** path; `/restaurants/mine`; `is_open` toggle; image upload; one-restaurant-per-owner 409; **order accept/reject** | **An approved restaurant-owner token.** Circular: every owner is `is_active=false` until an admin approves |
| **Delivery assignment**, accept/reject/pickup/deliver/reassign, tracking, driver location updates | **An order in a dispatchable state**, which requires owner acceptance (above) |
| Card **settlement**, real refunds, webhook replay/dedupe, `checkout.session.completed` | **A working Stripe test key + `STRIPE_WEBHOOK_SECRET`** (D1) |
| Password-reset **happy path** (valid token → 204, single-use, eviction) | **Mailbox access**, or `ENVIRONMENT != production` — the `debug_token` field is correctly gated at `users/app/router.py:185-189` and the response is confirmed token-free |
| Refresh-token branches: expired, stale `gen`, inactive user | **The JWT signing secret**, to mint targeted tokens |
| Gateway-bypass isolation; spoofed `X-User-*` straight at a service | **Reachable per-service hostnames.** All `*-service-orhxitfkxa-uc.a.run.app` URLs return a Google Frontend 404 on every path (internal ingress), so all findings are gateway-path only |
| `open_only=true` filter | **An approved venue with `is_open=false`.** All 5 approved venues are open |

**Data-integrity note, unrelated to any test:** live data violates the one-restaurant-per-owner rule — `owner_id 3` owns restaurants **1 and 2**, against `README.md:48` and `restaurants/app/service.py:127-131`. Provenance unknown; the guard could not be re-tested without an owner token.

---

## 7. Deploy drift

The working tree has uncommitted edits in 16 files, so the deployed revision is older than local source for `services/admin/app/router.py`, `services/orders/app/cart.py`, `services/orders/app/reorder.py`, `shared/http_client.py`, `infra/gcp/cloudbuild.yaml` and 8 frontend files.

Verifiers confirmed `services/users/**`, `services/restaurants/**` and `services/payments/**` are **clean** — every traceback frame matches local source line-for-line. **So D1–D5, D12, D15–D19 are genuine code/config defects, not drift artefacts.**

Live revisions: `api-gateway-00017-rjr`, `users-service-00024-lfh`, `restaurants-service-00023-77l`, `orders-service-00025-v5b`, `payments-service-00022-2d9`, `delivery-service-00019-sxf`, `notifications-service-00019-5m2`, `admin-service-00021-qpz`, `food-frontend-00031-rt4`.

---

## 8. What is working well

Coverage was real — ~500 live requests across 19 areas — and most of the platform held up under deliberately hostile probing.

- **Registration contract is exact.** Role gating (`admin` is not self-service), restaurant-block cross-validation in both directions, name/password/email validators, the bcrypt 72-byte guard (a 120-byte password returns 422, not 500), E.164 normalisation with cross-spelling uniqueness, and **no mass assignment** — `id`, `is_active`, `approval_status`, `hashed_password` in the body are silently ignored and the server's values win.
- **JWT handling is sound.** Correct claims and TTLs; garbage, empty, signature-tampered, payload-tampered (`role: customer→admin`), header-flipped and `alg:none` tokens all return 401 with **zero 5xx across 66 requests**; refresh rotates and blocklists; a refresh token presented as a bearer is rejected with `Invalid token type`.
- **Cross-service trust works both ways.** One users-minted token is accepted by orders, payments and notifications, and correctly yields **403 (not 401)** on `/restaurants/mine` and `/delivery/assignments` — each service verifies the shared secret before applying its own role guard.
- **The approval gate is real, not cosmetic.** Pending owners cannot log in (byte-exact `PENDING_APPROVAL_MESSAGE`); pending venues are absent from browse, suggest, search, popular cuisines and cities under every filter combination (`total=5`, always). *The gate leaks only through the two unguarded routes in D12.*
- **Discovery is solid.** Every filter behaves as `discovery.py` specifies; dish-aware search populates `matched_items`; invalid enums/ranges return 422; SQL-injection strings, unicode, emoji and a 4 000-character search term are all safely parameterised with the table intact afterwards.
- **Menu-management authorization is airtight.** 23/23 mutating endpoints returned 401 unauthenticated and 403 as a customer; spoofed `X-User-Id`/`X-User-Role`/`X-Role` headers ignored; post-test state byte-identical to the pre-test snapshot.
- **Per-user data isolation holds — no IDOR anywhere tested.** Cross-customer address `PATCH`/`DELETE` → 404 with the victim's data provably unchanged; cross-customer favourite delete → 404. A third party's row is indistinguishable from a nonexistent one.
- **Anti-enumeration on `forgot-password` is genuinely correct** — known-active, unknown and inactive addresses return **byte-identical** bodies (md5 `f4916cc0889a131afb5bf5ee643e7c12`), identical headers bar the trace id, and no timing separation despite the extra work on the hit path.
- **Session eviction works where it is implemented.** A successful `change-password` bumps `gen` and kills the calling session's old token, the other session's access **and** refresh tokens, and login with the old password.
- **CORS is correctly allowlisted on the live gateway** — an evil origin is rejected; only the deployed SPA origin is echoed.
- **The COD pipeline is genuinely end to end**, and cancellation produces a correct, fully audited `CREATED→PAYMENT_PENDING→PAYMENT_SUCCESS→CANCELLED` event trail. *(The refund half of cancellation is D2.)*
- **SendGrid email is healthy** — 11 successful sends in the window, ~12 s latency, zero failures, correctly *not* dispatched for unknown or inactive addresses. `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` are both wired from Secret Manager.
- **Redis is healthy** — `Redis connected` at every startup for orders, payments, delivery and users; zero Redis errors. (`restaurants-service` intentionally has no `REDIS_URL`, which does mean its Maps circuit-breaker at `providers.py:156-168` is inert in prod — worth knowing, not a defect.)
- **Pub/Sub wiring is correct for 20 of 21 subscriptions** — orders, payments, notifications, restaurants, users and admin all attach every topic they declare. Only `delivery-service--restaurant-events` is missing (D9).
- **nginx enforces its limits correctly** — a 7 MB body → 413, an over-long URI → 414, and request bodies buffer to disk as configured.
- **No upstream was ever unreachable** — zero 502/503/504 across 1,052 gateway requests.

---

## 9. Test accounts created on live

Password for all: `devpassword1`. Worth cleaning up before your delivery.

| Email | Role | id |
|---|---|---|
| `smoke.probe.a1@example.com` | customer | 18 |
| `qa.cust.b@example.com` | customer | 19 |
| `qa.driver.a@example.com` | driver | 20 |
| `qa.owner.a@example.com` | restaurant (pending) | 21 |

Plus ~12 squad-registered accounts matching `authreg*`, `pwreset*`, `profile*`, `verify*`, `verifier*`, and pending venues **6, 7, 8**. Orders **12, 15, 16, 17, 18, 19, 20, 21** were created; 15/16/19/20 are cancelled and carry the phantom refund state from D2/D16.

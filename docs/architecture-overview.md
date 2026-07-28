# Food Delivery System — Architecture Overview (MVP)

> This document is the **corrected, authoritative** architecture spec. It supersedes the
> original free-form blueprint, which contradicted itself (it declared a *"practical first
> version that intentionally avoids unnecessary enterprise-level details"* while simultaneously
> mandating full microservices, an Istio service mesh, 32-partition Kafka topics, multi-region
> DR, and 100k orders/minute). This document resolves those contradictions into one coherent
> plan and moves the maximalist material into a clearly-labelled **Future / Scale-Out** section
> that is explicitly **not** part of the first release.

---

## 1. Architecture Decision

**Build a modular monolith now, with service-ready domain boundaries.**

A single FastAPI application hosts one module per business domain
(`src/modules/{users,restaurants,cart,orders,payments,delivery,notifications}`). Each module:

- Owns its own tables and exposes a narrow internal service interface — **no module reaches
  into another module's tables directly.**
- Communicates with other modules through in-process function calls today, behind the same
  interface shape that a REST/Kafka call would take later.
- Can be lifted out into the standalone microservice the original blueprint envisioned, with no
  rewrite of business logic, once traffic or team size justifies the operational cost.

### Why not microservices on day one

The original blueprint's own stated goal is a *practical first version*. Standing up seven
independently deployed services, seven databases, a service mesh, and a schema registry before a
single order can be placed contradicts that goal, multiplies operational surface area, and slows
delivery of the core workflows. The domain boundaries below give us the *option* to split later;
YAGNI says we don't pay for it now.

```
                          +-------------------------------+
                          |     FastAPI application       |
                          |        (single process)       |
                          +-------------------------------+
                                        |
   +----------+----------+----------+----------+----------+----------+-------------+
   v          v          v          v          v          v          v             v
+------+  +--------+  +------+  +--------+  +---------+  +----------+  +---------------+
|users |  |restaur.|  | cart |  | orders |  |payments |  | delivery |  | notifications |
+------+  +--------+  +------+  +--------+  +---------+  +----------+  +---------------+
   |          |          |          |           |            |                |
   |          |          v          |           |            v                |
   |          |     [Redis: cart]   |           |     [Redis: driver GEO]      |
   +----------+---------------------+-----------+------------+----------------+
                                    |
                    [PostgreSQL — one DB, schema-per-domain]
                                    |
                     [Kafka — async events between domains]
```

**Data isolation in the monolith:** one PostgreSQL instance, one schema per domain
(`users`, `restaurants`, `orders`, …). Cross-schema foreign keys are disallowed; cross-domain
references are held by ID and resolved through the owning module's interface. This is what makes a
future physical split into database-per-service mechanical rather than a migration project.

---

## 2. Scope & Assumptions (unchanged from the original, restated for clarity)

- Customers browse restaurants, view menus, build a cart, place orders, pay online or by Cash on
  Delivery, and track order status.
- Restaurant users manage restaurant details, opening hours, menu categories/items, prices, and
  availability.
- A restaurant manually accepts or rejects each new order; no response within the configured
  window auto-cancels the order.
- One delivery partner handles one active order at a time in this version.
- A customer may cancel freely before the restaurant starts preparing; later cancellations need
  restaurant/support approval.
- One country, multiple cities.

---

## 3. Domains & Responsibilities

| Domain | Responsibility | Primary store |
|--------|----------------|---------------|
| Users | Registration, login, OTP, JWT issuance, profiles, roles, addresses | PostgreSQL (`users` schema) + Redis (OTP) |
| Restaurants | Profile, opening hours, categories, menu items, availability | PostgreSQL (`restaurants` schema) |
| Cart | Customer cart & transient checkout state | Redis |
| Orders | Order creation, item snapshot, state machine, cancellation, history | PostgreSQL (`orders` schema) |
| Payments | Payment initiation, PSP response, webhooks, refunds, idempotency | PostgreSQL (`payments` schema) + Redis (idempotency keys) |
| Delivery | Driver availability, assignment, delivery status, live location | PostgreSQL (`delivery` schema) + Redis GEO |
| Notifications | Push / SMS / email dispatch and delivery log | PostgreSQL (`notifications` schema) |

---

## 4. Technology Stack (MVP)

| Concern | Choice | Notes |
|---------|--------|-------|
| Backend | FastAPI (async) on Python 3.11–3.13 | Single deployable app |
| Relational DB | PostgreSQL 15, async via `asyncpg` | Schema-per-domain |
| Cache / ephemeral state | Redis 7 (async client from `redis-py`) | Cart, OTP, idempotency, driver GEO |
| Async events | Kafka (single broker locally) | Cross-domain events, outbox pattern |
| Auth | JWT (HS256 for MVP), OTP over SMS | See §7 |
| Local orchestration | Docker Compose | Postgres + Redis + Kafka + API |
| Tests | pytest, pytest-asyncio, Testcontainers | See §11 |

> **Correction applied to the codebase:** the scaffold pinned late-2023 dependency versions that
> do not install on Python 3.13 (`pydantic-core`, `psycopg2-binary` had no wheels and failed to
> build), depended on the **archived** `aioredis` package (which does not import on Python 3.11+),
> and omitted both `asyncpg` (required by the async DB engine) and `email-validator` (required by
> `EmailStr`). These were corrected — see `requirements.txt` / `pyproject.toml` and the change log
> in §13.

React front-ends (customer web, restaurant portal, admin) and NGINX as an edge gateway remain the
intended clients/entrypoint but are out of scope for backend MVP work.

---

## 5. Order State Machine

Canonical lifecycle:

```
CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS → RESTAURANT_ACCEPTED
        → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED → COMPLETED
```

Rules:

- Transitions are validated centrally; **skipping states is rejected** (e.g. `CREATED` →
  `OUT_FOR_DELIVERY` is invalid).
- Cash-on-Delivery skips the PSP capture step but still moves through `PAYMENT_PENDING` →
  `PAYMENT_SUCCESS` (payment recorded as collected on delivery).
- Terminal states: `COMPLETED`, `CANCELLED`, `REJECTED`.

### Cancellation & refund

| Cancel from state | Allowed | Refund |
|-------------------|---------|--------|
| `CREATED` / `PAYMENT_PENDING` / `PAYMENT_SUCCESS` | Yes (customer) | Full auto-refund |
| `RESTAURANT_ACCEPTED` | Yes (customer) | Full refund if kitchen hasn't started prep |
| `PREPARING` onward | Requires restaurant/support approval | No automatic refund (food-cost forfeit) |
| Any state, system-caused | Automatic | Full auto-refund |

System-caused reasons that always trigger a full refund: kitchen rejection, restaurant timeout,
no driver available, or payment/system failure.

---

## 6. Cart & Checkout Validation Pipeline

Checkout is rejected at the first failing gate:

1. Restaurant open? → else `RESTAURANT_CLOSED`
2. All items available? → else `ITEM_OUT_OF_STOCK`
3. Price hash matches current menu? → else `PRICE_MISMATCH_REFRESH`
4. Delivery address in a serviced zone? → else `ADDRESS_OUT_OF_ZONE`
5. Minimum order value met? → else `MIN_ORDER_NOT_MET`

On success, a validated, price-snapshotted order object is produced and handed to the Orders
domain.

---

## 7. Authentication & OTP

- OTP request is rate-limited per phone number. The OTP is **never stored in plaintext**: a
  salted SHA-256 hash is cached in Redis with a 120-second TTL and a max of 5 verification
  attempts.
- On successful verification the Users domain issues a JWT carrying identity + role.
- Clients send `Authorization: Bearer <JWT>`. In the monolith, a single auth dependency validates
  the token and injects the authenticated principal (`user_id`, `role`) into the request context;
  each module enforces its own RBAC against that principal. This is the same claims-propagation
  contract the blueprint described for a gateway — implemented in-process for now, movable to an
  NGINX/gateway edge later without changing module code.

> MVP note: HS256 (shared secret) is sufficient for a single app. The blueprint's JWKS/asymmetric
> validation belongs to the multi-service future (§12), where an edge gateway verifies tokens for
> independently deployed services.

---

## 8. Cross-Domain Events (Kafka + Outbox)

Domains that must react to each other asynchronously (e.g. Orders → Notifications, Payments →
Orders) communicate via Kafka. To avoid the dual-write problem, producers use a **transactional
outbox**: the domain writes its state change and an outbox row in the same DB transaction, and a
relay publishes outbox rows to Kafka.

MVP topics (single broker, small partition counts — **not** the blueprint's 32): `order-events`,
`payment-events`, `delivery-events`, `notification-events`, keyed by `order_id`. Failed consumes
retry with backoff and land in a dead-letter topic for inspection.

---

## 9. Saga for Order Placement

The Orders domain orchestrates the multi-step placement flow and compensates on failure:

| Forward step | Compensation on later failure |
|--------------|-------------------------------|
| Reserve cart items | Release cart items |
| Authorize payment | Refund / void payment |
| Confirm restaurant acceptance | (n/a — restaurant declines are a normal branch) |
| Assign driver | Release assignment, notify customer |

In the monolith this is an in-process orchestrator with persisted saga state; the step boundaries
match future service calls.

---

## 10. Non-Functional Targets (MVP — realistic)

The original blueprint's targets (99.99% uptime, 100k orders/min, 1M concurrent WebSockets,
<15 min multi-region failover) describe a mature, funded, multi-region platform — not a first
release. Right-sized MVP targets:

| Metric | MVP target |
|--------|-----------|
| Availability | 99.5% (single region, best-effort) |
| API latency (p95) | < 300 ms for menu/search/checkout |
| Payment checkout | < 3 s end-to-end |
| Throughput | Hundreds of orders/minute on a modest deployment |
| Recovery | Restore from daily backup + WAL; documented manual runbook |

The blueprint's aggressive numbers are retained as **aspirational scale-out goals** in §12.

---

## 11. Testing Strategy (MVP)

- **Unit tests** for domain logic (state machine, validation gates, refund rules) — no infra.
- **Integration tests** with Testcontainers spinning up real Postgres/Redis/Kafka.
- **API tests** through FastAPI's `TestClient`.
- Coverage goal: a pragmatic threshold on domain modules rather than the blueprint's blanket
  >85% across everything on day one.

E2E browser testing, k6/Locust load testing at 100k req/s, and chaos engineering are deferred
(§12).

---

## 12. Cloud & Deployment — Google Cloud Platform (GCP)

**Decision: GCP is the target cloud.** The MVP deploys serverless-first (Cloud Run); the same
container images move to GKE later when the monolith is split — no rewrite. Deploy config lives in
[`deploy/gcp/`](../deploy/gcp/) (Cloud Build pipeline + Cloud Run frontend image + setup guide).

Mapping from our stack to GCP managed services:

| Component | GCP service | Why |
|-----------|-------------|-----|
| FastAPI backend (container) | **Cloud Run** | Deploy our exact image; scales to zero, autoscales, HTTPS + no server ops |
| React build (static) | **Firebase Hosting** or **Cloud Storage + Cloud CDN** (Cloud Run nginx used in `deploy/gcp/` for uniformity) | Global CDN, free TLS, cheap |
| Docker images | **Artifact Registry** | Private registry + vulnerability scanning |
| PostgreSQL | **Cloud SQL for PostgreSQL** | Managed backups/PITR, HA, read replicas; connect via unix socket / private IP |
| Redis | **Memorystore for Redis** | Managed Redis over private IP (via Serverless VPC Access connector) |
| Kafka events | **Managed Service for Apache Kafka** (keeps Kafka API) or **Pub/Sub** | No broker ops; Managed Kafka keeps our producers/consumers unchanged |
| Secrets (JWT, DB URL, Stripe, Twilio) | **Secret Manager** | Versioned, IAM-scoped; injected into Cloud Run — no secrets in images (replaces Vault) |
| Object storage (menu images) | **Cloud Storage** | Cheap, CDN-frontable |
| Edge TLS / routing / WAF | **Cloud Load Balancing** + **Cloud Armor** | Gateway role + DDoS/WAF (replaces NGINX-gateway / Cloudflare) |
| Scheduled + deferred work | **Cloud Scheduler** + **Cloud Tasks** | Driver-assignment loop, restaurant-accept timeouts, notification retries |
| Notifications | **FCM** (push) + Twilio/SendGrid (SMS/email) | Native push; SMS/email stay third-party |
| Geo / ETA | **Google Maps Platform** | Geocoding, distance, delivery zones (M5) |
| CI/CD | **Cloud Build** (or GitHub Actions + Workload Identity Federation) | Test → build → push → deploy, keyless auth |
| Logs / metrics / traces | **Cloud Operations** (Logging, Monitoring, Trace) | Replaces ELK + Prometheus/Grafana; OpenTelemetry exports natively; alerts → PagerDuty |
| Private networking | **VPC** + **Serverless VPC Access** + **Cloud NAT** + **Cloud DNS** | Cloud Run reaches Cloud SQL/Memorystore privately |
| **Later:** microservices platform | **GKE Autopilot** + **Anthos Service Mesh** | Managed K8s + managed Istio when domains are split out |

**MVP footprint (stood up first):** Cloud Run · Firebase Hosting/Cloud Run · Cloud SQL ·
Memorystore · Secret Manager · Artifact Registry · Cloud Build. Kafka/Pub-Sub, Cloud Armor,
Scheduler/Tasks, and GKE arrive with M5/M6.

## 12a. Deferred scale-out (still not day-one)

- **Physical service split** into per-domain services with their own databases.
- **Edge gateway** doing JWT validation against JWKS (asymmetric keys) + identity header injection.
- **Kafka at scale:** 32 partitions/topic, idempotent producers, retry topics + DLQ, Schema Registry.
- **Real-time tracking:** driver GPS over WebSocket, Redis GEO, periodic Postgres sink, SSE to customer.
- **Resilience:** multi-region, tight RTO/RPO, read replicas, chaos drills, high-throughput load targets.

---

## 13. Corrections Applied to the Scaffold

Made while reviewing the existing code (no feature code added, nothing committed):

1. **`redis.py`** — replaced archived `aioredis` (crashes on import under Python 3.11+) with the
   async client from `redis-py` (`redis.asyncio`); guarded `get_redis`; used `aclose()`.
2. **`kafka.py`** — `send_event` no longer blocks the event loop (blocking send/flush runs via
   `asyncio.to_thread`); `init_kafka` no longer hard-fails startup when the broker is down; added
   a key serializer and producer retries.
3. **`jwt.py`** — replaced deprecated `datetime.utcnow()` with timezone-aware
   `datetime.now(timezone.utc)`.
4. **`database.py`** — removed the unused sync `create_engine` import.
5. **`config.py` / `schemas.py`** — migrated Pydantic v1 `class Config` to v2
   `SettingsConfigDict` / `ConfigDict`.
6. **Dependencies** — modernized stale late-2023 pins to a Python 3.13-compatible set; removed
   `aioredis`; **added `asyncpg`** (required by the async DB engine) and **`email-validator`**
   (via `pydantic[email]`, required by `EmailStr`); switched `kafka-python` (unmaintained on
   3.12+) to the `kafka-python-ng` fork.

Verification: `import src.main` succeeds, `python -m compileall src` is clean, and
`pytest` reports **2 passed, 0 warnings** on Python 3.13.

# food-delivery-system

A food delivery platform built as a **modular monolith** (FastAPI) with a **React + TypeScript** customer/owner web app. One deployable backend hosts a module per business domain (users, restaurants, cart, orders, payments, delivery, notifications) with service-ready boundaries.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (async), Python 3.11–3.13 |
| Database | PostgreSQL 15 (async via `asyncpg`), schema managed by **Alembic** |
| Cache / ephemeral state | Redis 7 (cart, idempotency, rate limits, token blocklist) |
| Events | Kafka (transactional outbox); tolerates the broker being absent |
| Auth | JWT (HS256) with refresh + revocation. Email and password only — no one-time codes, and no self-service password reset |
| Frontend | React 18, TypeScript, Vite, React Router, Framer Motion |
| Tests | pytest, pytest-asyncio, aiosqlite + fakeredis (unit), Testcontainers (integration) |
| Local orchestration | Docker Compose |

## Features

- **Customer:** register/login, browse restaurants & menus, add to cart, checkout (Cash on Delivery), track orders on a live status timeline, cancel before preparation, view notifications.
- **Restaurant owner:** create a restaurant, manage menu (categories + items, availability), accept/reject and advance orders.
- **Driver:** auto-assigned when an order is ready, pick up and deliver.
- **Platform:** validated order state machine, cancellation/refund rules, COD payment lifecycle (authorize → settle on delivery → refund), transactional outbox for cross-domain events, rate limiting, and an explicit CORS allowlist.

---

## Quick start (Docker — recommended)

Requires Docker Desktop. From the repository root:

```bash
./run.sh --seed
```

That builds and starts the whole stack — seven services, each with its own
PostgreSQL database, plus Redis, Kafka, the nginx gateway and the frontend — waits
for the gateway to answer, and creates a set of dev accounts.

| | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API gateway | http://localhost:8080 |
| A service's own docs (e.g. users) | http://localhost:8003/docs |

`--seed` gives you one account per role, all with password `devpassword1`:

| Email | Role |
|-------|------|
| `owner@example.com` | restaurant |
| `customer@example.com` | customer |
| `driver@example.com` | driver |
| `admin@example.com` | admin |

Seeding is separate from starting, and re-runnable, so you can do it any time:

```bash
./infra/compose/seed-dev.sh
```

Other things you will want:

```bash
./run.sh --logs     # follow the logs
./run.sh --down     # stop; volumes and data survive
./run.sh --reset    # stop and DELETE every volume (asks first)
```

> Each service is on its own port (`8001`–`8007`) for direct access and Swagger,
> but the frontend only ever talks to the gateway on `8080`. There is no single
> "the API" any more — that was the monolith.

---

## Local development (frontend on the host)

The backend is seven services with seven databases; running that outside Docker
is not worth the setup. The frontend is different — Vite's hot reload is the
difference between a one-second and a one-minute edit loop — so run the backend
in Docker and the frontend on your machine:

```bash
./run.sh              # backend stack in Docker
./run.sh --frontend   # Vite on the host, in a second terminal
```

The dev server proxies `/api/*` to the gateway on `http://localhost:8080` (see
`frontend/vite.config.ts`), so no CORS setup is needed in dev.

### Working on a single service

To iterate on backend code, rebuild just that service — the others keep running:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --build users-service
```

Its tests need no infrastructure at all (SQLite and a fake Redis):

```bash
./services/test.sh users     # one service
./services/test.sh           # all seven, one process each
uv run pytest                # the shared package
```

---

## Environment variables

Copy `.env.example` to `.env` and adjust as needed. Key settings:

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection (async driver added automatically) | `postgresql://fooduser:foodpass@localhost:5432/fooddelivery` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | JWT signing secret — **change in production** | `change-me` |
| `CORS_ORIGINS` | Comma-separated allowlist (never `*` with credentials) | `http://localhost:5173` |
| `AUTH_RATE_MAX` / `AUTH_RATE_WINDOW_SECONDS` | Login/register rate limit | `10` / `60` |
| `RESTAURANT_ACCEPT_TIMEOUT_SECONDS` | Auto-cancel window for unaccepted orders | `300` |
| `KAFKA_BROKERS` | Broker list for the compose stack | `kafka:9092` |
| `MESSAGING_TRANSPORT` | `kafka` locally, `pubsub` on Cloud Run — see `shared/messaging.py` | `kafka` |

The frontend reads `VITE_API_URL` (see `frontend/.env.example`); leave it unset in dev to use the Vite proxy.

---

## Database migrations (Alembic)

The schema is managed by Alembic — it is **not** created at application startup.

```bash
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back the latest migration
alembic revision --autogenerate -m "describe change"   # create a new migration
alembic current               # show the currently-applied revision
```

Compose runs `alembic upgrade head` automatically before starting the API. Tests create their own in-memory schema and do not require migrations.

---

## Running tests

The test suite bootstraps its own env (in-memory SQLite + fake Redis), so no setup is needed:

```bash
pytest                         # full suite with coverage
pytest -m "not integration"    # skip the Testcontainers (Docker) tests
pytest tests/modules/orders    # a single module
```

Integration tests (`-m integration`) spin up a real PostgreSQL via Testcontainers and are skipped automatically when Docker is unavailable.

Frontend type-check + build:

```bash
cd frontend && npm run build
```

Lint the backend:

```bash
flake8 src
```

---

## Trying the full flow

1. Register a **restaurant** account → go to **Manage** → create a restaurant, set it **Open**, add a category and menu items.
2. Register a **customer** account → browse to the restaurant → **Add** items → open **Cart** → add a delivery address (in the same city) → **Place order (COD)**.
3. Track the order under **Orders**; it starts at *Confirmed* (COD payment recorded).
4. As the restaurant, accept and advance the order; mark it **Ready for pickup**.
5. Register a **driver** account (self-registration supported) → it is auto-assigned the ready order → pick up and deliver. The customer sees the timeline update and the payment settle.

---

## Continuous integration

`.github/workflows/ci.yml` runs on push/PR: backend lint (`flake8 src`), a Postgres+Redis-backed migration up/down/up check, the full test suite, and a frontend type-check + build.

## Project layout

```
src/
  core/            # jwt, security, exceptions, rate limiting
  adapters/        # database, redis, kafka clients — how the app reaches backing services
  modules/
    users/         # auth, profiles, addresses, roles
    restaurants/   # profiles, categories, menu items
    cart/          # Redis cart + 5-gate checkout validation
    orders/        # persisted orders, state machine, cancellation/refund
    payments/      # COD lifecycle + provider abstraction (Stripe-ready)
    delivery/      # driver assignment + pickup/deliver
    notifications/ # per-status customer notifications (log channel)
    events/        # transactional outbox + Kafka relay
alembic/           # migrations
infra/             # build & deploy artifacts — Docker, compose, Cloud Build
  compose/         #   local stack (docker-compose.yml)
  docker/          #   API + frontend images, nginx config
  gcp/             #   Cloud Build pipeline, Cloud Run frontend image
frontend/src/      # React app (pages, api bindings, auth + cart context)
tests/             # unit (sqlite/fakeredis) + integration (Testcontainers)
docs/              # architecture, implementation plan, specs & plans
```

# food-delivery-system

A food delivery platform built as a **modular monolith** (FastAPI) with a **React + TypeScript** customer/owner web app. One deployable backend hosts a module per business domain (users, restaurants, cart, orders, payments, delivery, notifications) with service-ready boundaries.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (async), Python 3.11–3.13 |
| Database | PostgreSQL 15 (async via `asyncpg`), schema managed by **Alembic** |
| Cache / ephemeral state | Redis 7 (cart, OTP, idempotency, rate limits, token blocklist) |
| Events | Kafka (transactional outbox); tolerates the broker being absent |
| Auth | JWT (HS256) with refresh + revocation; OTP over SMS (stubbed in dev) |
| Frontend | React 18, TypeScript, Vite, React Router, Framer Motion |
| Tests | pytest, pytest-asyncio, aiosqlite + fakeredis (unit), Testcontainers (integration) |
| Local orchestration | Docker Compose |

## Features

- **Customer:** register/login (password or OTP), browse restaurants & menus, add to cart, checkout (Cash on Delivery), track orders on a live status timeline, cancel before preparation, view notifications.
- **Restaurant owner:** create a restaurant, manage menu (categories + items, availability), accept/reject and advance orders.
- **Driver:** auto-assigned when an order is ready, pick up and deliver.
- **Platform:** validated order state machine, cancellation/refund rules, COD payment lifecycle (authorize → settle on delivery → refund), transactional outbox for cross-domain events, rate limiting, and an explicit CORS allowlist.

---

## Quick start (Docker — recommended)

Requires Docker Desktop. From the repository root:

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, the API (which runs `alembic upgrade head` before serving), and the frontend.

| Service | URL |
|---------|-----|
| Frontend (customer/owner web app) | http://localhost:5173 |
| API | http://localhost:8000 |
| Interactive API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

Stop with `Ctrl+C`; remove containers/volumes with `docker compose down -v`.

> Kafka is disabled by default in the compose file (`KAFKA_BROKERS=disabled`); the app runs fine without it. Event publishing is a no-op until a broker is configured.

---

## Local development (without Docker for the app)

Run the databases in Docker, and the backend + frontend on your machine for hot reload.

### 1. Start infrastructure

```bash
docker compose up -d postgres redis
```

### 2. Backend

```bash
# from the repo root
python -m venv .venv
# activate it:
#   Windows PowerShell:  .venv\Scripts\Activate.ps1
#   macOS/Linux:         source .venv/bin/activate
pip install -e ".[dev]"

# configuration (pydantic loads .env automatically)
cp .env.example .env

# create the schema, then run the API
alembic upgrade head
uvicorn src.main:app --reload
```

The API is now on http://localhost:8000 (docs at `/docs`).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The app is on http://localhost:5173 and proxies `/api/*` to the backend at `http://localhost:8000` (see `vite.config.ts`), so no CORS setup is needed in dev.

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
| `KAFKA_BROKERS` | Broker list, or `disabled` to turn events off | `disabled` |

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

`docker compose up` runs `alembic upgrade head` automatically before starting the API. Tests create their own in-memory schema and do not require migrations.

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
  infrastructure/  # database, redis, kafka
  modules/
    users/         # auth, OTP, profiles, addresses, roles
    restaurants/   # profiles, categories, menu items
    cart/          # Redis cart + 5-gate checkout validation
    orders/        # persisted orders, state machine, cancellation/refund
    payments/      # COD lifecycle + provider abstraction (Stripe-ready)
    delivery/      # driver assignment + pickup/deliver
    notifications/ # per-status customer notifications (log channel)
    events/        # transactional outbox + Kafka relay
alembic/           # migrations
frontend/src/      # React app (pages, api bindings, auth + cart context)
tests/             # unit (sqlite/fakeredis) + integration (Testcontainers)
docs/              # architecture, implementation plan, specs & plans
```

# food-delivery-system

A food delivery platform built as **seven FastAPI microservices** behind an nginx
gateway, with a **React + TypeScript** web app for customers, restaurant owners,
drivers and admins.

Each service owns its own database and its own migration chain. Nothing reaches
across a boundary with a query: services talk over HTTP where an answer is needed
now, and over events where it is not. A foreign key cannot cross a service, which
is the constraint that keeps the split honest.

| Service | Port | Owns |
|---------|------|------|
| `users` | 8003 | accounts, auth, profiles, addresses, favourites |
| `restaurants` | 8004 | venues, approval status, menus, stock, reviews |
| `orders` | 8001 | cart, checkout validation, the order state machine |
| `payments` | 8002 | COD and card lifecycle, refunds, Stripe webhooks |
| `delivery` | 8005 | driver roster, assignment, pickup and delivery |
| `notifications` | 8006 | outbound email/SMS and the in-app feed |
| `admin` | 8007 | operator console read-models and stats |
| `api-gateway` | 8080 | the one public door; routes `/api/*` to the above |
| `frontend` | 5173 | the SPA |

The per-service ports exist for direct access and Swagger (`http://localhost:8003/docs`).
The frontend only ever talks to the gateway on `8080` — there is no single "the API".

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (async), Python 3.11–3.13 |
| Databases | PostgreSQL 15 per service (async via `asyncpg`), each with its own Alembic chain |
| Cache / ephemeral state | Redis 7 (cart, idempotency, rate limits, reset tokens, token blocklist) |
| Events | Kafka locally, Pub/Sub on Cloud Run — same code, chosen at deploy time (`shared/messaging.py`). Every publish goes through a transactional outbox |
| Auth | JWT (HS256), refresh + revocation + session-generation eviction. Email and password, with self-service password reset |
| Payments | Cash on delivery, and card via Stripe hosted Checkout |
| Frontend | React 18, TypeScript, Vite, React Router, Framer Motion |
| Tests | pytest, pytest-asyncio, aiosqlite + fakeredis; Vitest + Testing Library |
| Local orchestration | Docker Compose |
| Deploy | Cloud Build → Cloud Run, Cloud SQL, Pub/Sub, Secret Manager |

## Features

- **Customer:** register/login, reset a forgotten password, browse and search
  restaurants (dish-aware, with city/cuisine/rating/price/veg/open filters),
  cart, checkout by cash or card, live order timeline, cancel before
  preparation, reviews, favourites, notifications.
- **Restaurant owner:** register **one** restaurant, which starts *pending* and
  is invisible to customers until an admin approves it. Then: menu categories
  and items, stock, cover photos, food type, address and contact, delivery
  radius, open/closed, and accepting and advancing orders.
- **Driver:** auto-assigned when an order is ready; pick up and deliver.
- **Admin:** approve or reject restaurant registrations, a full restaurant list
  (owner, contact, status, rating, reviews), platform stats, any order, and the
  acceptance-timeout sweep. Admins **cannot** register a restaurant — owners do
  that themselves.
- **Platform:** validated order state machine, cancellation and refund rules,
  transactional outbox for every cross-service event, per-service read-models,
  circuit-broken HTTP between services, rate limiting, CORS allowlist.

---

## Quick start

Requires Docker Desktop. From the repository root:

```bash
./run.sh --seed
```

That builds and starts everything — seven services, seven PostgreSQL databases,
Redis, Kafka, the gateway and the frontend — waits for the gateway to answer, then
creates one account per role.

| | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API gateway | http://localhost:8080 |

`--seed` accounts, all with password `devpassword1`:

| Email | Role |
|-------|------|
| `owner@example.com` | restaurant |
| `customer@example.com` | customer |
| `driver@example.com` | driver |
| `admin@example.com` | admin |

Seeding is separate from starting and safe to re-run — an existing account is
reused, never replaced:

```bash
./infra/compose/seed-dev.sh
```

Everything else:

```bash
./run.sh --logs     # follow the logs
./run.sh --down     # stop; volumes and your data survive
./run.sh --reset    # stop and DELETE every volume (asks first)
```

> `--reset` empties the users database, which is how every account, address and
> favourite disappears while the other services keep rows pointing at ids that no
> longer resolve. Re-seed afterwards.

---

## Local development

The backend is seven services with seven databases; running that outside Docker
is not worth the setup. The frontend is different — Vite's hot reload is the
difference between a one-second and a one-minute edit loop:

```bash
./run.sh              # backend stack in Docker
./run.sh --frontend   # Vite on the host, second terminal
```

The dev server proxies `/api/*` to the gateway (see `frontend/vite.config.ts`),
so no CORS setup is needed in dev.

### Working on one service

Rebuild just that service; the rest keep running:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --build users-service
docker compose -f infra/compose/docker-compose.yml logs -f users-service
```

---

## Tests

No infrastructure needed — every suite uses in-memory SQLite and a fake Redis.

```bash
uv run pytest                # the shared package (identity, messaging, outbox, http client)
./services/test.sh           # all seven services
./services/test.sh orders    # just one
uv run flake8 shared services
```

`services/test.sh` runs **one process per service**, and that is not a style
choice: every service has a package literally named `app`, so a single pytest
run would import one of them and quietly serve that same module to every other
service's tests.

Frontend:

```bash
cd frontend
npm test              # Vitest + Testing Library
npm run build         # tsc type-check, then the production build
```

---

## Database migrations

Each service owns its own Alembic chain under `services/<name>/alembic/`. There
is no global migration, and no schema is created at startup.

```bash
# One service, against its own database.
./services/migrate.sh users upgrade head
./services/migrate.sh users downgrade -1

# Local convenience only — production has every service migrate itself.
./services/migrate.sh all upgrade head
```

To write one:

```bash
cd services/users
DATABASE_URL=... uv run --project ../.. alembic revision -m "describe change"
```

Autogenerate is deliberately unavailable: a service's chain spells its tables out
in full so it runs anywhere the service's container runs, without importing
another service's models.

> **Never run `alembic downgrade base` against a database you care about.** It
> drops every table, including `outbox_events`. Use `downgrade -1`.

CI round-trips every chain (`upgrade → downgrade base → upgrade`) against a real
Postgres, so a migration that cannot be undone fails there rather than in
production.

---

## Configuration

Two templates, for two different things:

| File | For |
|------|-----|
| `.env.services.example` | the compose stack — per-service database URLs, Postgres credentials, the JWT secret |
| `.env.example` | third-party integrations and tunables shared across services |

```bash
cp .env.services.example .env.services
cp .env.example .env
```

Settings worth knowing:

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET_KEY` | Signs and verifies every token. The same value in every service — **change it in production** |
| `CORS_ORIGINS` | Browser origins allowed to call the users service. Never `*`, because these routes carry credentials |
| `MESSAGING_TRANSPORT` | `kafka` locally, `pubsub` on Cloud Run |
| `AUTH_RATE_MAX` / `AUTH_RATE_WINDOW_SECONDS` | Login, register and reset rate limit |
| `PASSWORD_RESET_TTL_SECONDS` | How long an emailed reset link stays usable |
| `FRONTEND_BASE_URL` | Where reset links point, and where Stripe returns a customer |
| `RESTAURANT_ACCEPT_TIMEOUT_SECONDS` | Auto-cancel window for unaccepted orders |

Third-party integrations — Stripe, SendGrid, Twilio, Google Maps — are **all
optional**. Unset, the feature degrades rather than failing: SMS and email log
instead of sending, card payments fall back to a deterministic stand-in
provider, and addresses stay ungeocoded.

---

## Trying the full flow

1. **Owner** (`owner@example.com`) → **Manage** → register a restaurant. It is
   *pending*, so customers cannot see it yet. Build the menu while you wait.
2. **Admin** (`admin@example.com`) → **Manage restaurants** → Approve it.
3. **Owner** → set the restaurant **Open**, add a category and items with stock.
4. **Customer** (`customer@example.com`) → browse → add to cart → add a delivery
   address in the same city → place the order.
5. **Owner** → accept it, advance it, mark **Ready for pickup**.
6. **Driver** (`driver@example.com`) → it is auto-assigned → pick up → deliver.
   The customer's timeline updates and the payment settles.

---

## Continuous integration and deploy

`.github/workflows/ci.yml` runs on every push and PR:

- `flake8 shared services`
- every service's migration chain round-tripped against a real Postgres
- the shared suite, then each service's suite in its own process
- frontend tests, type-check and build

A push to `main` additionally deploys via
[`infra/gcp/cloudbuild.yaml`](infra/gcp/cloudbuild.yaml): tests → build nine
images → provision Pub/Sub topics and subscriptions → run each service's
migrations as a Cloud Run job → deploy the services, the gateway, then the
frontend.

First-time setup is [`docs/deploy-runbook.md`](docs/deploy-runbook.md). Two
things about the pipeline are worth knowing before you touch it: it **bootstraps
in two passes** (the gateway needs service URLs that do not exist until the first
deploy), and migrations run as **Cloud Run jobs**, not build steps, because a
build step has no route to a private Cloud SQL instance.

---

## Project layout

```
services/
  users/           # auth, profiles, addresses, favourites
  restaurants/     # venues, approval, menus, stock, reviews
  orders/          # cart, checkout gates, order state machine
  payments/        # COD + Stripe, refunds, webhooks
  delivery/        # driver roster, assignment, pickup/deliver
  notifications/   # email/SMS senders + in-app feed
  admin/           # operator read-models and stats
    app/           #   the service itself
    alembic/       #   its own migration chain
    tests/         #   its own suite, one process
  test.sh          # run every service's suite
  migrate.sh       # run a service's migrations

shared/            # what every service copies into its image
  identity.py      #   verifying a JWT, without a users table
  messaging.py     #   Kafka or Pub/Sub behind one interface
  outbox.py        #   transactional outbox + relay
  http_client.py   #   service-to-service calls with a circuit breaker
  errors.py, phone.py, ratelimit.py

frontend/src/      # React app (pages, api bindings, auth + cart context)
infra/
  compose/         # local stack + seed-dev.sh
  docker/          # service and frontend images, nginx gateway config
  nginx/           # gateway routing
  gcp/             # Cloud Build pipeline, secrets script, Cloud Run images
docs/              # architecture, roles and permissions, deploy runbook
```

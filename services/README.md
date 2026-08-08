# Services

Six services, each with its own process, database, migration chain and deploy.
The monolith (`src/`) is still in the repository but no longer in the request
path: the frontend talks to the gateway, which routes to these.

| Service | Port | Database | Consumes | Publishes |
|---|---|---|---|---|
| users | 8003 | `users_db` | — | `user-events`, `user-contact-events`, `address-events`, `notification-events` |
| restaurants | 8004 | `restaurants_db` | `order-events` | `restaurant-events`, `notification-events` |
| orders | 8001 | `orders_db` | `payment-events`, `delivery-events`, `address-events`, `restaurant-events`, `user-events` | `order-events`, `notification-events`, `payment-commands` |
| payments | 8002 | `payments_db` | `order-events` | `payment-events` |
| delivery | 8005 | `delivery_db` | `order-events`, `user-events` | `delivery-events`, `notification-events` |
| notifications | 8006 | `notifications_db` | `order-events`, `notification-events`, `user-contact-events` | — |
| admin | 8007 | `admin_db` | everything | — |

**One synchronous call exists on purpose.** Checkout asks the restaurants
service to validate and reserve, because the customer is waiting and an order
cannot be priced without an answer. It is guarded by a timeout and a circuit
breaker ([`shared/http_client.py`](../src/shared/http_client.py)) and fails as a
503, which says "retry" rather than "you were wrong". Everything else is events.

**Contact details live in one place.** `user-events` carries a name and a role
and anyone may subscribe. Email and phone go to `user-contact-events`, read only
by the two services with a reason to hold them: notifications, which sends to an
address, and admin, which shows one to an operator.

**The cut-over is a switch, not an overlap.** The monolith and the orders service
both number orders from 1, so two publishers on `order-events` means a consumer
cannot tell one order #3 from another. `KAFKA_BROKERS=disabled:9092` on the
monolith is what enforces one publisher at a time.

## notifications — the first extracted service

Its own process, its own database, its own deploy. Chosen first because nothing
calls it synchronously: it only consumes events, so if it is down no order
fails.

```
services/notifications/
  Dockerfile          # built from the repo root; copies src/shared as shared/
  app/
    main.py           # FastAPI + lifespan; /health (alive) vs /ready (can serve)
    config.py         # its own settings — not the platform's
    db.py             # one engine, one database: notifications_db
    models.py         # its own Base; every user_id is a bare int
    consumer.py       # Kafka consumer for order-events
    service.py        # handles an event; loads no User, because it cannot
    router.py         # same paths as before, guarded by Identity not User
    auth.py           # JWTAuth built from this service's own secret
```

**Auth without a users service.** Tokens are verified locally against the shared
secret — see [`src/shared/identity.py`](../src/shared/identity.py). Calling the
users service on every request would have made it a synchronous dependency of
the whole platform, so its downtime would be everyone's. The cost is that a
revocation reaches a service only when the access token expires; keeping that
lifetime short is the mitigation.

**It owns contact details.** `order-events` carries a customer id, not an
address; where to send is resolved from this service's own `contacts`
read-model, fed by the restricted `user-contact-events` topic. An earlier
version put email and phone on the order event, which meant every consumer of
that topic ended up storing them — orders holding an address it never sends to.

### Trying the isolation claim

```bash
docker compose -f infra/compose/docker-compose.yml up -d
docker compose stop notifications-service    # place an order — still succeeds
docker compose start notifications-service   # the backlog is delivered
```

---

# Service migrations

Each service owns its schema and its own migration chain. Nothing here imports
`src/` — a service whose migrations reached back into the monolith's models
would have to be deployed alongside it, which is the coupling the split exists
to remove.

```
services/<name>/
  alembic.ini
  alembic/
    env.py              # reads DATABASE_URL; no src import, no autogenerate
    versions/           # this service's chain, starting at 0001
```

Autogenerate is deliberately unavailable: with no live metadata to diff against,
revisions are written by hand. That is the cost of independence, and it is the
same cost every service pays.

## Running them

```bash
# one service
./services/migrate.sh notifications upgrade head

# all of them, local setup only
./services/migrate.sh all upgrade head
```

In production each service migrates itself as part of its own deploy. `all` is a
local convenience; a single command that migrates everything is a single command
that can break everything.

## Who owns what

| Database | Tables |
|---|---|
| `users_db` | `users`, `addresses`, `favorites` |
| `restaurants_db` | `restaurants`, `menu_categories`, `menu_items`, `reviews` |
| `orders_db` | `orders`, `order_items`, `order_status_events` |
| `payments_db` | `payments` |
| `delivery_db` | `deliveries` |
| `notifications_db` | `notifications`, `notification_preferences`, `device_tokens`, `contacts` |
| `admin_db` | `user_rows`, `restaurant_rows`, `order_rows` — all read-models |

Plus `outbox_events` in every one. It is per-service on purpose: a shared outbox
would put every service back on one table — one lock, one failure domain.

Two placements worth stating, since neither is obvious:

- **`reviews` sits with restaurants**, not orders. The read that matters is
  "this restaurant's rating", and it happens on every listing. Beside the
  restaurant, that read stays inside one service.
- **`favorites` sits with users.** Every read of it is "my favourites".

`cart` needs no table — it is Redis-backed.

## Foreign keys

A foreign key cannot cross a database, so the split is decided by which of the
monolith's 21 survive. Eight do; the other thirteen became plain indexed
integers, validated by the application instead of the database:

| Kept (same database) | Dropped (cross-service) |
|---|---|
| `addresses.user_id` | `orders.customer_id`, `.restaurant_id`, `.address_id` |
| `favorites.user_id` | `payments.order_id` |
| `menu_categories.restaurant_id` | `deliveries.order_id`, `.driver_id` |
| `menu_items.restaurant_id`, `.category_id` | `notifications.user_id` |
| `reviews.restaurant_id` | `notification_preferences.user_id` |
| `order_items.order_id` | `device_tokens.user_id` |
| `order_status_events.order_id` | `restaurants.owner_id` |
| | `reviews.order_id`, `.customer_id` |
| | `favorites.restaurant_id` |

Uniqueness survives the FK's removal where it was carrying real meaning —
`payments.order_id`, `deliveries.order_id` and `reviews.order_id` are still
unique indexes, so "one payment per order" is still enforced by the database
that owns payments.

## Tests

```bash
./services/test.sh            # every service
./services/test.sh orders     # one of them
```

One process per service, and that is not a style choice: every service has a
package literally named `app`, so a single pytest process would import one of
them and then quietly serve that same module to every other service's tests.
Separate processes keep the isolation the split is for, including in the test
run. CI runs the same script.

Each suite is in-memory — SQLite and a fake Redis, with any other service
stubbed at the HTTP layer. A service whose tests need a live stack is a service
nobody runs the tests for.

What they cover is mostly what the split introduced, because that is what was
new and untested: read-model handlers (applying an event twice must be
harmless), the one synchronous call and each way it can fail, and which fields
do and do not appear on each topic.

## Verifying a chain

Every chain round-trips — `upgrade head` → `downgrade base` → `upgrade head` —
against real Postgres. A chain that cannot be undone cannot be rolled back in
production either. All of them pass today.

## Read-models

Four services keep local copies of another service's facts, updated from events,
because the alternative — calling that service per request — would make this one
fail whenever it does. A read-model is allowed to be slightly stale. It is never
allowed to be authoritative.

| Service | Copies | To answer |
|---|---|---|
| orders | addresses, restaurants, customers | where to deliver, who may accept, whose name is on a review |
| delivery | orders, drivers | where to navigate, who is free |
| restaurants | orders | may this person review this order |
| payments | orders | what to charge |
| admin | everything | the console, without fanning out |

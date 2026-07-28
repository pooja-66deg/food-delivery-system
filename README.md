# food-delivery-system
Scalable Food Delivery System built using Microservices Architecture.

## Database migrations

The database schema is managed by **Alembic** — it is no longer created at
application startup. Before running the API against a real database, apply the
migrations:

```bash
# env vars must be set (see .env.example): DATABASE_URL, REDIS_URL, JWT_SECRET_KEY
alembic upgrade head
```

`docker compose up` runs `alembic upgrade head` automatically before starting
the API container. Common commands:

```bash
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back the latest migration
alembic revision --autogenerate -m "describe change"   # create a new migration
alembic current               # show the currently-applied revision
```

Tests run against an in-memory SQLite database and create their schema directly
(see `tests/conftest.py`), so they do not require migrations.

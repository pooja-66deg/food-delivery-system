"""The restaurants service.

The catalogue: venues, menus, stock, and the reviews that rate them.

It is the most *read* service on the platform — every browse, search and
restaurant page hits it — and the one place where the split accepts a
synchronous dependency: checkout asks it whether a restaurant is open and what a
dish costs, because an order genuinely cannot be priced without an answer. That
call belongs to the orders service and is guarded there with a timeout and a
breaker; nothing here calls out.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.consumer import start_consumer, stop_consumer
from app.db import async_session, engine
from app.models import OutboxEvent
from app.internal import router as internal_router
from app.review_router import router as reviews_router
from app.router import router
from shared.cors import install_cors
from shared.errors import install_error_handlers
from shared.messaging import publisher_for
from shared.outbox import OutboxRelay, relay_for

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

_relay: OutboxRelay | None = None
_publisher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _relay, _publisher
    import asyncio

    logger.info("%s starting", settings.service_name)
    # Schema is Alembic's job, run as a deploy step — never created at runtime.
    start_consumer(asyncio.get_running_loop())
    try:
        _publisher = publisher_for(
            transport=settings.messaging_transport,
            kafka_servers=settings.kafka_bootstrap_servers,
            project_id=settings.google_cloud_project,
        )
        _relay = relay_for(async_session, OutboxEvent, _publisher)
        _relay.start()
    except Exception:  # noqa: BLE001 — a broker outage must not stop the catalogue
        logger.exception("Outbox relay could not start; events will queue until restart")

    yield

    logger.info("%s shutting down", settings.service_name)
    stop_consumer()
    if _relay is not None:
        await _relay.stop()
    if _publisher is not None:
        _publisher.close()
    await engine.dispose()


app = FastAPI(title="Restaurants Service", version="0.1.0", lifespan=lifespan)

# The browser checks every response this service returns through the gateway
# against the SPA's origin, which is a different hostname. nginx forwards what
# we send and adds nothing, so the header has to originate here.
install_cors(app, settings.cors_origin_list)
install_error_handlers(app)

# Uploaded images, in development. This service writes them (storage.py) so this
# service serves them — the monolith used to, and a split that moved the writer
# without moving the reader leaves every image 404ing.
#
# Never reached in production: ENVIRONMENT=production uploads to GCS and the
# stored URL is absolute, so the browser goes straight there.
os.makedirs(settings.media_root, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")
# Before the public router, and it matters: that one owns /restaurants/{id},
# which would otherwise swallow /restaurants/lookup and try to parse "lookup"
# as an integer. FastAPI matches in registration order.
app.include_router(internal_router)
app.include_router(router)
app.include_router(reviews_router)


@app.get("/health", tags=["ops"])
async def health():
    """Is the process alive? Deliberately checks nothing else.

    If this reported on the database too, a database blip would make the
    orchestrator kill and restart a perfectly healthy process — which is how a
    dependency outage becomes an outage of its own.
    """
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready", tags=["ops"])
async def ready():
    """Can it actually serve? This one does check the database."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Not ready: %s", exc)
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ready"}

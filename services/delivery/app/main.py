"""The delivery service.

Assignment and tracking. Consumes order events; nothing calls it to place an order.

Two liveness facts the gateway needs to tell apart: ``/health`` says the process
is alive, ``/ready`` says it can serve. A service whose database is unreachable
is up but not ready, and routing traffic to it turns a fast failure into a
hanging request.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.config import settings
from app.db import async_session, engine
from app.consumer import start_consumer, stop_consumer
from app.models import OutboxEvent
from app.redis_client import close_redis, init_redis
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
    logger.info("%s starting", settings.service_name)
    # Schema is Alembic's job, run as a deploy step — never created at runtime.
    import asyncio

    # Redis first, so the consumer can assign to the *nearest* driver from its
    # first event rather than falling back to any free one.
    await init_redis()
    start_consumer(asyncio.get_running_loop())
    # Without this the service records every delivery event and publishes none —
    # so a driver's pickup never reaches orders, and an order sits at
    # READY_FOR_PICKUP forever while the food is already in a bag.
    try:
        _publisher = publisher_for(
            transport=settings.messaging_transport,
            kafka_servers=settings.kafka_bootstrap_servers,
            project_id=settings.google_cloud_project,
        )
        _relay = relay_for(async_session, OutboxEvent, _publisher)
        _relay.start()
    except Exception:  # noqa: BLE001 — a broker outage must not stop deliveries
        logger.exception("Outbox relay could not start; events will queue until restart")

    yield
    logger.info("%s shutting down", settings.service_name)
    stop_consumer()
    if _relay is not None:
        await _relay.stop()
    if _publisher is not None:
        _publisher.close()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="Delivery Service", version="0.1.0", lifespan=lifespan)

# The browser checks every response this service returns through the gateway
# against the SPA's origin, which is a different hostname. nginx forwards what
# we send and adds nothing, so the header has to originate here.
install_cors(app, settings.cors_origin_list)
install_error_handlers(app)
app.include_router(router)


@app.get("/health", tags=["ops"])
async def health():
    """Is the process alive? Deliberately checks nothing else.

    If this reported on the database too, a database blip would make the
    orchestrator kill and restart a perfectly healthy process — which is how a
    dependency outage becomes an outage of its own.
    """
    return {"status": "ok", "service": settings.service_name}


@app.get("/ready", tags=["ops"])
async def ready(response: Response):
    """Can it actually serve? This one does check the database."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Not ready: %s", exc)
        # 503, not a 200 that merely says "degraded" in its body. Cloud Run and
        # Kubernetes route on the status code and read nothing else, so the old
        # response advertised this instance as ready to serve while its database
        # was unreachable — every request sent here failed, and the load balancer
        # kept sending them because it had been told everything was fine.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ready"}

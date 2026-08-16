"""The notifications service.

Its own process, its own database, its own deploy. The first service split out
of the monolith, chosen because nothing calls it synchronously: if this process
is not running, no order fails — the events wait in Kafka and are delivered when
it comes back.

Two liveness facts worth separating, because the gateway needs to tell them
apart: ``/health`` says the process is up, ``/ready`` says it can serve. A
service whose database is unreachable is up but not ready, and routing traffic
to it turns a fast failure into a hanging request.
"""

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.config import settings
from app.consumer import start_consumer, stop_consumer
from app.db import engine
from app.router import router
from shared.cors import install_cors

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    logger.info("%s starting", settings.service_name)
    # Schema is Alembic's job (services/notifications/alembic), run as a deploy
    # step — never created at runtime.
    start_consumer(asyncio.get_running_loop())
    yield
    logger.info("%s shutting down", settings.service_name)
    stop_consumer()
    await engine.dispose()


app = FastAPI(title="Notifications Service", version="0.1.0", lifespan=lifespan)

# The browser checks every response this service returns through the gateway
# against the SPA's origin, which is a different hostname. nginx forwards what
# we send and adds nothing, so the header has to originate here.
install_cors(app, settings.cors_origin_list)
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

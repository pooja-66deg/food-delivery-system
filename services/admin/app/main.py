"""The admin service.

The operator console: what the platform did, across every service.

It is the only service that reads broadly, and it pays for that with local
copies rather than fan-out calls — so the console still reports when a service
is down, using what it last heard. It publishes nothing; the one action it
offers is forwarded to the service that owns the data.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.clients import close_clients
from app.config import settings
from app.consumer import start_consumer, stop_consumer
from app.db import engine
from app.router import router
from shared.errors import install_error_handlers

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    logger.info("%s starting", settings.service_name)
    # Schema is Alembic's job, run as a deploy step — never created at runtime.
    start_consumer(asyncio.get_running_loop())
    yield
    logger.info("%s shutting down", settings.service_name)
    stop_consumer()
    await close_clients()
    await engine.dispose()


app = FastAPI(title="Admin Service", version="0.1.0", lifespan=lifespan)
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
async def ready():
    """Can it actually serve? This one does check the database."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Not ready: %s", exc)
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ready"}

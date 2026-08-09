"""The users service.

Identity: registration, login, tokens, profile, addresses, favourites.

It is the service everything else depends on and the one nothing calls. That is
deliberate and it is the whole design: every other service verifies tokens
locally against the shared secret and keeps its own read-model of whatever it
needs about a user. So this service publishes constantly and consumes almost
nothing — and when it is down, the rest of the platform keeps serving requests
from tokens this service issued earlier.

"Almost": it subscribes to ``restaurant-events`` and to nothing else. A
restaurant applicant registers inactive and is let in when an operator approves
their venue, and that decision is made in the restaurants service against a row
in another database. Consuming it keeps the direction of dependency intact —
restaurants still does not call this service — at the cost of the one thing this
module used to be able to claim. See app/consumer.py.

What does stop while it is down: signing up, logging in, and anything else that
needs a *new* token. That is the honest, bounded blast radius.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.consumer import start_consumer, stop_consumer
from app.db import async_session, engine
from app.models import OutboxEvent
from app.redis_client import close_redis, init_redis
from app.favorites import router as favorites_router
from app.router import auth_router, users_router
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
    await init_redis()

    # The relay is what turns recorded events into published ones. Without it
    # this service still works and still records — and every consumer's copy of
    # a user silently stops updating, which is the kind of failure that shows up
    # weeks later as "why is this driver's name wrong".
    try:
        _publisher = publisher_for(
            transport=settings.messaging_transport,
            kafka_servers=settings.kafka_bootstrap_servers,
            project_id=settings.google_cloud_project,
        )
        _relay = relay_for(async_session, OutboxEvent, _publisher)
        _relay.start()
    except Exception:  # noqa: BLE001 — a broker outage must not stop signups
        logger.exception("Outbox relay could not start; events will queue until restart")

    # Inbound, and there is only one: an operator's approval decision, which is
    # what turns a registered restaurant applicant into an account that can sign
    # in. If this does not start, approvals are not lost — they wait on the topic
    # and land when it does.
    start_consumer(asyncio.get_running_loop())

    yield

    logger.info("%s shutting down", settings.service_name)
    stop_consumer()
    if _relay is not None:
        await _relay.stop()
    if _publisher is not None:
        _publisher.close()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="Users Service", version="0.1.0", lifespan=lifespan)

# CORS. The deploy has always set CORS_ORIGINS and the docs have always called it
# required, but nothing read it and no middleware was installed — so in
# production the browser was rejecting cross-origin auth calls and the setting
# was doing nothing about it.
#
# Only this service needs it: every other service sits behind the gateway on the
# gateway's own origin, and the browser never talks to them directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Credentialed requests, which is why the origin list is explicit and never
    # "*" — the combination is what Starlette refuses and browsers reject.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_error_handlers(app)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(favorites_router)


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

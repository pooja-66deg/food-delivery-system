"""Redis: the cart, and the per-user checkout lock.

Shared infrastructure rather than another service — but this one cannot shrug it
off. The cart *is* the Redis entry, and the checkout lock is what stops a double
tap creating two orders. Without it there is no honest way to serve either, so
the dependency raises 503 rather than returning None and letting each call site
invent an answer.
"""

import logging
from redis.asyncio import Redis

from app.config import settings
from shared.errors import ServiceUnavailableException

logger = logging.getLogger(__name__)

_client: Redis | None = None


async def init_redis() -> None:
    global _client
    try:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
        await _client.ping()
        logger.info("Redis connected")
    except Exception as exc:  # noqa: BLE001 — degraded, not dead
        logger.warning("Redis unavailable, running without it: %s", exc)
        _client = None


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get_redis() -> Redis:
    """FastAPI dependency. Raises 503 rather than returning None.

    503 is the honest answer: the request could not be served and retrying is
    right — unlike a 4xx, which would tell the caller their request was wrong.
    """
    if _client is None:
        raise ServiceUnavailableException("Cart store is unavailable")
    return _client

"""Redis for the webhook replay-dedupe set.

Shared infrastructure rather than another service. Losing it costs this service
its guard against Stripe redelivering an event — so callers treat a ``None``
client as "cannot dedupe" and the webhook handler decides what that means,
rather than every call site inventing its own answer.
"""

import logging
from typing import Optional

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[Redis] = None


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


async def get_redis() -> Optional[Redis]:
    """FastAPI dependency. May be None — every caller must cope with that."""
    return _client

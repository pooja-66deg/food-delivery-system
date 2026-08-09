"""Redis: auth rate-limit counters, and the revocation blocklist every other
service reads.

Shared infrastructure, not another service. It once held credentials too — OTP
challenges and single-use reset tokens — and those routes had to fail honestly
when it was down because a challenge had nowhere else to live. Nothing here is a
credential now, but a 503 is still the honest answer: without the blocklist a
logged-out token would be honoured, so serving the request would be worse than
refusing it.
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
    except Exception as exc:  # noqa: BLE001 — surfaced per-request, not at boot
        logger.warning("Redis unavailable at startup: %s", exc)
        _client = None


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get_redis() -> Redis:
    """FastAPI dependency. Raises 503 rather than returning None.

    A 503 is the honest answer: the request could not be served and retrying is
    the right response — unlike a 4xx, which would tell the caller their request
    was wrong when it was not.
    """
    if _client is None:
        raise ServiceUnavailableException("Session store is unavailable")
    return _client

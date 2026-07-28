"""Redis client setup.

Uses the async client shipped with redis-py (``redis.asyncio``). The legacy
``aioredis`` package is archived and does not import on Python 3.11+, so it must
not be used here.
"""

from typing import Optional

import redis.asyncio as redis

from src.config import settings

redis_client: Optional[redis.Redis] = None


async def init_redis() -> redis.Redis:
    """Initialize the Redis connection pool."""
    global redis_client
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return redis_client


async def get_redis() -> redis.Redis:
    """Return the initialized Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return redis_client


async def close_redis() -> None:
    """Close the Redis connection."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None

"""A minimal fixed-window rate limiter backed by Redis."""
from redis.asyncio import Redis

from .errors import TooManyRequestsException


async def enforce_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int) -> None:
    """Increment a counter for ``key`` and raise once it exceeds ``limit`` within
    the window. First hit in a window sets the TTL."""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        raise TooManyRequestsException("Too many attempts. Please try again later.")

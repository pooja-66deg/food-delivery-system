"""The other services this one calls.

There is exactly one, and it is worth keeping it that way. Every other thing
orders needs from elsewhere arrives as an event; the restaurants service is the
sole exception, because checkout cannot price an order without an answer and the
customer is waiting for it.

Constructed lazily and kept for the process lifetime so the connection pool and
— more importantly — the circuit breaker's state survive between requests. A
breaker rebuilt per call would never open.
"""

from typing import Optional

from app.config import settings
from shared.http_client import CircuitBreaker, ServiceClient

_restaurants: Optional[ServiceClient] = None


def restaurants() -> ServiceClient:
    global _restaurants
    if _restaurants is None:
        _restaurants = ServiceClient(
            settings.restaurants_service_url,
            name="restaurants-service",
            timeout_seconds=settings.restaurants_timeout_seconds,
            breaker=CircuitBreaker(
                threshold=settings.breaker_threshold,
                cooldown_seconds=settings.breaker_cooldown_seconds,
            ),
        )
    return _restaurants


async def close_clients() -> None:
    global _restaurants
    if _restaurants is not None:
        await _restaurants.aclose()
        _restaurants = None

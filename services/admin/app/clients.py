"""The one service the console calls.

Everything on the stats and listing pages is answered locally. The single
exception is running the acceptance-timeout sweep, which is an *action* on
orders, not a report about them — and an action belongs to the service that owns
the data it changes.

The timeout is generous compared to checkout's: a sweep over every pending order
is legitimately slower than pricing a cart, and an operator who pressed a button
will wait a few seconds for it.
"""

from typing import Optional

from app.config import settings
from shared.http_client import CircuitBreaker, ServiceClient

_orders: Optional[ServiceClient] = None


def orders() -> ServiceClient:
    global _orders
    if _orders is None:
        _orders = ServiceClient(
            settings.orders_service_url,
            name="orders-service",
            timeout_seconds=settings.orders_timeout_seconds,
            breaker=CircuitBreaker(
                threshold=settings.breaker_threshold,
                cooldown_seconds=settings.breaker_cooldown_seconds,
            ),
        )
    return _orders


async def close_clients() -> None:
    global _orders
    if _orders is not None:
        await _orders.aclose()
        _orders = None

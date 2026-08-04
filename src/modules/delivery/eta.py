"""ETA assembly: which legs a delivery has, and the per-order cache.

The provider knows nothing about deliveries and the service knows nothing about
routing mechanics. This module is the only place the two meet.
"""
import json
import logging

from src.config import settings
from src.modules.delivery.models import DeliveryStatus
from src.modules.delivery.providers import (
    Coordinate,
    RouteEstimate,
    RoutingProvider,
    routing_provider,
)

logger = logging.getLogger(__name__)

# From PICKED_UP onward the food is aboard, so the restaurant is behind the
# driver and including it would inflate every ETA.
_CARRYING = (DeliveryStatus.PICKED_UP.value, DeliveryStatus.DELIVERED.value)


def cache_key(order_id: int) -> str:
    return f"delivery:eta:{order_id}"


def waypoints_for(
    status: str,
    driver: Coordinate | None,
    restaurant: Coordinate | None,
    destination: Coordinate | None,
) -> list[Coordinate]:
    """The journey still ahead of the driver, as an ordered waypoint list.

    Returns ``[]`` when fewer than two points are known, which is the signal
    that no ETA can be computed rather than an error.
    """
    if status in _CARRYING:
        candidates = [driver, destination]
    else:
        candidates = [driver, restaurant, destination]
    points = [point for point in candidates if point is not None]
    return points if len(points) >= 2 else []


async def estimate_for_order(
    redis,
    order_id: int,
    waypoints: list[Coordinate],
    provider: RoutingProvider | None = None,
) -> RouteEstimate | None:
    """A cached route estimate for one order.

    The driver's position is deliberately *not* cached — it is read fresh from
    the GEO index on every request. Position is cheap and local; routing is a
    metered network call, so only the latter is cached.
    """
    if len(waypoints) < 2:
        return None

    if redis is not None:
        cached = await redis.get(cache_key(order_id))
        if cached:
            try:
                return RouteEstimate(**json.loads(cached))
            except (ValueError, TypeError) as exc:
                logger.warning("Discarding unreadable cached ETA (%s)", exc)

    estimate = await (provider or routing_provider(redis)).route(waypoints)
    if estimate is None:
        return None

    if redis is not None:
        await redis.set(
            cache_key(order_id),
            json.dumps(estimate.__dict__),
            ex=settings.delivery_eta_cache_seconds,
        )
    return estimate


async def invalidate(redis, order_id: int) -> None:
    """Drop a cached ETA after anything that changes the route.

    Called on every delivery status change, so the leg switch at pickup and a
    driver swap on reject both land on the next poll rather than up to
    ``delivery_eta_cache_seconds`` later.
    """
    if redis is not None:
        await redis.delete(cache_key(order_id))

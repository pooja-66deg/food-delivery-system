"""ETA leg selection and the per-order Redis cache."""
import pytest

from src.modules.delivery import eta
from src.modules.delivery.models import DeliveryStatus
from src.modules.delivery.providers import Coordinate, RouteEstimate

DRIVER = Coordinate(latitude=12.9716, longitude=77.5946)
RESTAURANT = Coordinate(latitude=12.9352, longitude=77.6245)
DESTINATION = Coordinate(latitude=12.9000, longitude=77.6000)


class CountingProvider:
    def __init__(self, estimate=RouteEstimate(2.5, 9, "estimate")):
        self.estimate = estimate
        self.calls = 0

    async def route(self, waypoints):
        self.calls += 1
        return self.estimate


def test_before_pickup_routes_via_the_restaurant():
    points = eta.waypoints_for(
        DeliveryStatus.ACCEPTED.value, DRIVER, RESTAURANT, DESTINATION
    )
    assert points == [DRIVER, RESTAURANT, DESTINATION]


def test_after_pickup_routes_straight_to_the_customer():
    points = eta.waypoints_for(
        DeliveryStatus.PICKED_UP.value, DRIVER, RESTAURANT, DESTINATION
    )
    assert points == [DRIVER, DESTINATION]


def test_missing_points_are_dropped():
    points = eta.waypoints_for(
        DeliveryStatus.ACCEPTED.value, DRIVER, None, DESTINATION
    )
    assert points == [DRIVER, DESTINATION]


def test_too_few_points_yields_no_route():
    assert eta.waypoints_for(DeliveryStatus.ACCEPTED.value, None, None, DESTINATION) == []
    assert eta.waypoints_for(DeliveryStatus.PICKED_UP.value, DRIVER, None, None) == []


@pytest.mark.asyncio
async def test_estimate_returns_none_without_enough_waypoints(fake_redis):
    provider = CountingProvider()
    assert await eta.estimate_for_order(fake_redis, 1, [], provider=provider) is None
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_estimate_caches_by_order(fake_redis):
    provider = CountingProvider()
    points = [DRIVER, DESTINATION]

    first = await eta.estimate_for_order(fake_redis, 42, points, provider=provider)
    second = await eta.estimate_for_order(fake_redis, 42, points, provider=provider)

    assert first == second
    assert provider.calls == 1  # second read came from Redis


@pytest.mark.asyncio
async def test_cached_estimate_round_trips_every_field(fake_redis):
    provider = CountingProvider(RouteEstimate(12.005, 18, "google"))
    points = [DRIVER, DESTINATION]

    await eta.estimate_for_order(fake_redis, 7, points, provider=provider)
    cached = await eta.estimate_for_order(fake_redis, 7, points, provider=provider)

    assert cached.distance_km == pytest.approx(12.005)
    assert cached.duration_minutes == 18
    assert cached.source == "google"


@pytest.mark.asyncio
async def test_invalidate_forces_a_recompute(fake_redis):
    provider = CountingProvider()
    points = [DRIVER, DESTINATION]

    await eta.estimate_for_order(fake_redis, 9, points, provider=provider)
    await eta.invalidate(fake_redis, 9)
    await eta.estimate_for_order(fake_redis, 9, points, provider=provider)

    assert provider.calls == 2


@pytest.mark.asyncio
async def test_unreadable_cache_entry_is_discarded_not_fatal(fake_redis):
    provider = CountingProvider()
    await fake_redis.set(eta.cache_key(11), "not json")

    estimate = await eta.estimate_for_order(
        fake_redis, 11, [DRIVER, DESTINATION], provider=provider
    )

    assert estimate is not None
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_estimate_survives_a_missing_redis():
    provider = CountingProvider()
    estimate = await eta.estimate_for_order(
        None, 1, [DRIVER, DESTINATION], provider=provider
    )
    assert estimate is not None
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_invalidate_survives_a_missing_redis():
    await eta.invalidate(None, 1)  # must not raise

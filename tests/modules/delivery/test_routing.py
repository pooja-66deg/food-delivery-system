"""Routing providers: haversine fallback and the Google Routes adapter."""
import json

import httpx
import pytest

from src.config import settings
from src.modules.delivery.providers import (
    MAPS_DISABLED_KEY,
    Coordinate,
    GoogleRoutesProvider,
    HaversineRouting,
    haversine_km,
    routing_provider,
)

PALERMO = Coordinate(latitude=38.115, longitude=13.361)
CATANIA = Coordinate(latitude=37.502, longitude=15.087)

OK_BODY = {"routes": [{"distanceMeters": 12005, "duration": "1062s"}]}


def _transport(handler):
    return httpx.MockTransport(handler)


def test_haversine_matches_known_distance():
    assert haversine_km(PALERMO, CATANIA) == pytest.approx(166.24, abs=0.5)


def test_haversine_is_symmetric_and_zero_for_same_point():
    assert haversine_km(PALERMO, CATANIA) == pytest.approx(haversine_km(CATANIA, PALERMO))
    assert haversine_km(PALERMO, PALERMO) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_haversine_route_applies_winding_factor_and_speed():
    # 166.24 km * 1.3 winding = 216.1 km; at 25 km/h that is 519 minutes.
    estimate = await HaversineRouting().route([PALERMO, CATANIA])
    assert estimate is not None
    assert estimate.distance_km == pytest.approx(216.1, abs=1.0)
    assert estimate.duration_minutes == pytest.approx(519, abs=3)
    assert estimate.source == "estimate"


@pytest.mark.asyncio
async def test_haversine_route_sums_intermediate_legs():
    mid = Coordinate(latitude=37.8, longitude=14.2)
    direct = await HaversineRouting().route([PALERMO, CATANIA])
    via = await HaversineRouting().route([PALERMO, mid, CATANIA])
    assert via.distance_km > direct.distance_km


@pytest.mark.asyncio
async def test_haversine_route_floors_duration_at_one_minute():
    almost = Coordinate(latitude=38.1150, longitude=13.3611)
    estimate = await HaversineRouting().route([PALERMO, almost])
    assert estimate.duration_minutes == 1


@pytest.mark.asyncio
async def test_haversine_route_needs_two_waypoints():
    assert await HaversineRouting().route([]) is None
    assert await HaversineRouting().route([PALERMO]) is None


# ── the Google Routes adapter ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_google_parses_distance_and_duration():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Goog-Api-Key")
        return httpx.Response(200, json=OK_BODY)

    provider = GoogleRoutesProvider(api_key="test-key", transport=_transport(handler))
    estimate = await provider.route([PALERMO, CATANIA])

    # 12005 m, rounded to the two decimals the payload carries.
    assert estimate.distance_km == pytest.approx(12.005, abs=0.01)
    assert estimate.duration_minutes == 18  # ceil(1062 / 60)
    assert estimate.source == "google"
    assert "computeRoutes" in seen["url"]
    assert seen["key"] == "test-key"


@pytest.mark.asyncio
async def test_google_sends_intermediate_waypoints():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    mid = Coordinate(latitude=37.8, longitude=14.2)
    provider = GoogleRoutesProvider(api_key="k", transport=_transport(handler))
    await provider.route([PALERMO, mid, CATANIA])

    assert len(seen["body"]["intermediates"]) == 1
    assert seen["body"]["travelMode"] == "DRIVE"


@pytest.mark.asyncio
async def test_google_omits_intermediates_for_a_two_point_route():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    provider = GoogleRoutesProvider(api_key="k", transport=_transport(handler))
    await provider.route([PALERMO, CATANIA])

    assert "intermediates" not in seen["body"]


@pytest.mark.asyncio
async def test_google_falls_back_to_haversine_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow")

    provider = GoogleRoutesProvider(api_key="k", transport=_transport(handler))
    estimate = await provider.route([PALERMO, CATANIA])
    assert estimate.source == "estimate"


@pytest.mark.asyncio
async def test_google_falls_back_on_server_error():
    provider = GoogleRoutesProvider(
        api_key="k", transport=_transport(lambda r: httpx.Response(503, text="nope"))
    )
    estimate = await provider.route([PALERMO, CATANIA])
    assert estimate.source == "estimate"


@pytest.mark.asyncio
async def test_google_falls_back_on_malformed_body():
    provider = GoogleRoutesProvider(
        api_key="k", transport=_transport(lambda r: httpx.Response(200, json={"routes": []}))
    )
    estimate = await provider.route([PALERMO, CATANIA])
    assert estimate.source == "estimate"


@pytest.mark.asyncio
async def test_google_403_sets_suppression_flag_and_skips_further_calls(fake_redis):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})

    provider = GoogleRoutesProvider(
        api_key="k", transport=_transport(handler), redis=fake_redis
    )

    first = await provider.route([PALERMO, CATANIA])
    assert first.source == "estimate"
    assert await fake_redis.get(MAPS_DISABLED_KEY) is not None

    second = await provider.route([PALERMO, CATANIA])
    assert second.source == "estimate"
    assert calls["n"] == 1  # the second call never reached the network


@pytest.mark.asyncio
async def test_google_needs_two_waypoints():
    provider = GoogleRoutesProvider(
        api_key="k", transport=_transport(lambda r: httpx.Response(200, json=OK_BODY))
    )
    assert await provider.route([PALERMO]) is None


@pytest.mark.asyncio
async def test_routing_provider_selects_by_configured_key(monkeypatch):
    assert isinstance(routing_provider(), HaversineRouting)
    monkeypatch.setattr(settings, "google_maps_api_key", "configured")
    assert isinstance(routing_provider(), GoogleRoutesProvider)

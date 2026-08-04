"""Routing and geocoding providers for delivery tracking.

Only this module talks to Google. Callers depend on the ``RoutingProvider`` and
``GeocodeProvider`` protocols, so the deterministic fallbacks are what the tests
exercise and a missing API key is a configuration state rather than a failure.
"""
import logging
import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
# Straight-line distance understates a road journey. 1.3 is the usual urban
# detour ratio and keeps the fallback honest rather than optimistic.
ROAD_WINDING_FACTOR = 1.3


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RouteEstimate:
    distance_km: float
    duration_minutes: int
    source: str  # "google" | "estimate"


class RoutingProvider(Protocol):
    async def route(self, waypoints: list[Coordinate]) -> RouteEstimate | None: ...


def haversine_km(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance between two coordinates, in kilometres."""
    lat1, lon1, lat2, lon2 = map(
        math.radians, (a.latitude, a.longitude, b.latitude, b.longitude)
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


class HaversineRouting:
    """Distance and duration with no network call.

    Runs when Google is unconfigured or unreachable, and is what the tests
    assert against because it is exact and deterministic.
    """

    async def route(self, waypoints: list[Coordinate]) -> RouteEstimate | None:
        if len(waypoints) < 2:
            return None
        straight = sum(haversine_km(a, b) for a, b in zip(waypoints, waypoints[1:]))
        distance_km = straight * ROAD_WINDING_FACTOR
        speed = settings.delivery_average_speed_kmh or 25.0
        minutes = math.ceil(distance_km / speed * 60)
        return RouteEstimate(
            distance_km=round(distance_km, 2),
            duration_minutes=max(1, minutes),
            source="estimate",
        )


ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters"
REQUEST_TIMEOUT_SECONDS = 8.0

# Set after a configuration failure (403 / PERMISSION_DENIED). A disabled API,
# revoked key, or lapsed billing returns the same response on every retry, so
# stop asking for a while instead of paying a doomed round trip per ETA.
MAPS_DISABLED_KEY = "delivery:maps_disabled"
MAPS_DISABLED_TTL_SECONDS = 600


class _MapsMisconfigured(Exception):
    """A permission failure that retrying cannot fix."""


def _waypoint(coord: Coordinate) -> dict:
    return {
        "location": {
            "latLng": {"latitude": coord.latitude, "longitude": coord.longitude}
        }
    }


class GoogleRoutesProvider:
    """Google Routes API adapter, degrading to haversine on any failure.

    ``transport`` exists so tests can drive the real request-building code
    against a stub instead of patching the client.
    """

    def __init__(self, api_key: str, transport=None, redis=None) -> None:
        self._api_key = api_key
        self._transport = transport
        self._redis = redis
        self._fallback = HaversineRouting()

    async def route(self, waypoints: list[Coordinate]) -> RouteEstimate | None:
        if len(waypoints) < 2:
            return None
        if await self._suppressed():
            return await self._fallback.route(waypoints)
        try:
            return await self._request(waypoints)
        except _MapsMisconfigured:
            await self._suppress()
            return await self._fallback.route(waypoints)
        except Exception as exc:  # transient: timeout, 5xx, malformed body
            logger.warning("Routes API call failed (%s); using estimate", exc)
            return await self._fallback.route(waypoints)

    async def _request(self, waypoints: list[Coordinate]) -> RouteEstimate:
        body = {
            "origin": _waypoint(waypoints[0]),
            "destination": _waypoint(waypoints[-1]),
            "travelMode": "DRIVE",
        }
        if len(waypoints) > 2:
            body["intermediates"] = [_waypoint(w) for w in waypoints[1:-1]]

        async with httpx.AsyncClient(
            transport=self._transport, timeout=REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                ROUTES_URL,
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": ROUTES_FIELD_MASK,
                },
                json=body,
            )

        if response.status_code == 403:
            raise _MapsMisconfigured(response.text[:200])
        response.raise_for_status()

        route = response.json()["routes"][0]
        seconds = int(str(route["duration"]).rstrip("s"))
        return RouteEstimate(
            distance_km=round(route["distanceMeters"] / 1000, 2),
            duration_minutes=max(1, math.ceil(seconds / 60)),
            source="google",
        )

    async def _suppressed(self) -> bool:
        if self._redis is None:
            return False
        return await self._redis.get(MAPS_DISABLED_KEY) is not None

    async def _suppress(self) -> None:
        logger.warning(
            "Google Maps rejected the configured key; falling back to estimated "
            "ETAs for %ss. Check that the Routes API is enabled and billing is "
            "active on the key's project.",
            MAPS_DISABLED_TTL_SECONDS,
        )
        if self._redis is not None:
            await self._redis.set(MAPS_DISABLED_KEY, "1", ex=MAPS_DISABLED_TTL_SECONDS)


def routing_provider(redis=None) -> RoutingProvider:
    """Google when a key is configured, haversine otherwise."""
    if settings.google_maps_api_key:
        return GoogleRoutesProvider(settings.google_maps_api_key, redis=redis)
    return HaversineRouting()


GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeocodeProvider(Protocol):
    async def geocode(
        self, line1: str, city: str, postal_code: str
    ) -> Coordinate | None: ...


class NullGeocoder:
    """Default when no key is configured: addresses stay ungeocoded."""

    async def geocode(
        self, line1: str, city: str, postal_code: str
    ) -> Coordinate | None:
        logger.debug("Geocoding skipped: no Google Maps key configured")
        return None


class GoogleGeocoder:
    """Google Geocoding API adapter. Returns None rather than raising, because
    an address that will not geocode must still save."""

    def __init__(self, api_key: str, transport=None) -> None:
        self._api_key = api_key
        self._transport = transport

    async def geocode(
        self, line1: str, city: str, postal_code: str
    ) -> Coordinate | None:
        # line2 is deliberately excluded: apartment and unit numbers do not
        # improve a geocode and frequently defeat it.
        address = ", ".join(part for part in (line1, city, postal_code) if part)
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=REQUEST_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(
                    GEOCODE_URL, params={"address": address, "key": self._api_key}
                )
            response.raise_for_status()
            body = response.json()
            if body.get("status") != "OK" or not body.get("results"):
                logger.info("Geocoding returned %s for %r", body.get("status"), address)
                return None
            point = body["results"][0]["geometry"]["location"]
            return Coordinate(latitude=point["lat"], longitude=point["lng"])
        except Exception as exc:
            logger.warning("Geocoding failed for %r (%s)", address, exc)
            return None


def geocode_provider() -> GeocodeProvider:
    """Google when a key is configured, a no-op otherwise."""
    if settings.google_maps_api_key:
        return GoogleGeocoder(settings.google_maps_api_key)
    return NullGeocoder()

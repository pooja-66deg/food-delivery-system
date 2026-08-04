# Live Driver Tracking & ETA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the customer a live Google map of their driver with a real ETA, and give the driver a consent-based switch that publishes their position.

**Architecture:** ETAs are computed server-side behind a `RoutingProvider` protocol — Google Routes API when a key is configured, haversine otherwise — and returned inside the existing tracking payload, which the frontend already polls every 5 seconds. Delivery addresses gain nullable coordinates, geocoded on save, so the journey has an endpoint. Every geographic value is nullable and every consumer degrades rather than erroring.

**Tech Stack:** FastAPI (async), SQLAlchemy 2.0, Alembic, Redis (GEO index + ETA cache), httpx, pytest/pytest-asyncio/fakeredis, React 18 + TypeScript, Vite, Vitest + Testing Library, `@vis.gl/react-google-maps`.

**Spec:** `docs/superpowers/specs/2026-08-04-delivery-tracking-design.md`

## Global Constraints

- **Git is the human's job.** Do NOT run `git add`, `git commit`, `git push`, or any other git write command. Each task ends with a *suggested* commit message as text for the human to run. This overrides the commit steps in the writing-plans template.
- **No `Co-Authored-By:` trailer** and no tool-attribution footer in any suggested commit message.
- **TDD, always.** Write the failing test, run it, watch it fail for the right reason, then implement.
- `flake8 src` must stay clean. Max line length is defined in `.flake8` — check it before writing long lines.
- `pytest` must stay green. Never leave a red suite between tasks.
- Enums are `class X(str, Enum)` stored as `String` columns. Money is `Numeric(10, 2)` / `Decimal`.
- Never reintroduce runtime `create_all` in `src/main.py`. Model changes require an Alembic migration.
- Time-dependent logic takes `now` as a parameter. Do not call `datetime.now()` inside logic under test.
- Coordinates are `float`, always nullable, and `None` propagates to `None` — never to `0.0` and never to an exception.
- Config values already exist in `src/config.py`: `google_maps_api_key`, `delivery_average_speed_kmh` (25.0), `delivery_eta_cache_seconds` (30). Do not re-add them.
- Frontend imports shared UI from `'../components/ui'` (the barrel in `frontend/src/components/ui/index.ts`). Add new shared components there; page-specific ones live next to the page.
- Frontend tests live in `frontend/tests/`, mirroring `src/`. `src/` stays production code only.

## File Structure

**Backend — create**
- `src/modules/delivery/providers.py` — `Coordinate`, `RouteEstimate`, the two protocols, `HaversineRouting`, `GoogleRoutesProvider`, `NullGeocoder`, `GoogleGeocoder`, and the two factories. All outbound HTTP for maps lives here and nowhere else.
- `src/modules/delivery/eta.py` — domain glue: which waypoints a delivery needs, plus the Redis ETA cache. Knows about `Delivery`; knows nothing about HTTP.
- `alembic/versions/0008_address_coordinates.py`
- `tests/modules/delivery/test_routing.py`, `tests/modules/delivery/test_eta.py`
- `tests/modules/users/test_address_geocoding.py`

**Backend — modify**
- `src/modules/users/models.py` — `Address.latitude` / `Address.longitude`
- `src/modules/users/schemas.py` — `AddressResponse` gains both fields
- `src/modules/users/profile.py` — geocode on create, re-geocode on address change
- `src/modules/delivery/schemas.py` — `CoordinateRead`, `TrackingRead`
- `src/modules/delivery/service.py` — enriched `tracking_for_order`, ETA invalidation
- `src/modules/delivery/router.py` — `response_model=TrackingRead`
- `tests/conftest.py` — unset `google_maps_api_key`
- `tests/modules/delivery/test_location.py:79` — `location` → `driver`

**Frontend — create**
- `frontend/src/lib/useDriverLocation.ts` — geolocation watch + throttled POSTs
- `frontend/src/components/DeliveryMap.tsx` — map with text fallback
- `frontend/tests/lib/useDriverLocation.test.ts`, `frontend/tests/components/DeliveryMap.test.tsx`

**Frontend — modify**
- `frontend/src/api/delivery.ts` — `Tracking` type, `location` → `driver`
- `frontend/src/pages/DriverPage.tsx` — share-location toggle, next-stop link
- `frontend/src/pages/OrderDetailPage.tsx` — render `DeliveryMap`
- `frontend/package.json` — add `@vis.gl/react-google-maps`

---

### Task 1: Haversine routing provider

**Files:**
- Create: `src/modules/delivery/providers.py`
- Create: `tests/modules/delivery/test_routing.py`
- Modify: `tests/conftest.py:50-55`

**Interfaces:**
- Consumes: nothing.
- Produces: `Coordinate(latitude: float, longitude: float)`, `RouteEstimate(distance_km: float, duration_minutes: int, source: str)`, `RoutingProvider` protocol with `async route(waypoints: list[Coordinate]) -> RouteEstimate | None`, `HaversineRouting()`, `haversine_km(a, b) -> float`, `EARTH_RADIUS_KM`, `ROAD_WINDING_FACTOR`.

- [ ] **Step 1: Add the Google key to the credential-clearing fixture**

In `tests/conftest.py`, add `"google_maps_api_key"` to the tuple in `_no_third_party_credentials` (after `"fcm_server_key"`). Without this, every test on your machine would call the live Google API, because your `.env` has a working key.

```python
    for field in (
        "stripe_api_key", "stripe_secret_key", "stripe_webhook_secret",
        "twilio_account_sid", "twilio_auth_token", "twilio_phone_number",
        "sendgrid_api_key", "sendgrid_from_email", "fcm_server_key",
        "google_maps_api_key",
    ):
```

- [ ] **Step 2: Write the failing tests**

Create `tests/modules/delivery/test_routing.py`. The Palermo→Catania pair is the same one `test_location.py` already uses; its true great-circle distance is 166.24 km.

```python
"""Routing providers: haversine fallback and the Google Routes adapter."""
import pytest

from src.modules.delivery.providers import (
    Coordinate,
    HaversineRouting,
    haversine_km,
)

PALERMO = Coordinate(latitude=38.115, longitude=13.361)
CATANIA = Coordinate(latitude=37.502, longitude=15.087)


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/modules/delivery/test_routing.py -q --no-cov`
Expected: collection error — `ModuleNotFoundError: No module named 'src.modules.delivery.providers'`.

- [ ] **Step 4: Write the implementation**

Create `src/modules/delivery/providers.py`:

```python
"""Routing and geocoding providers for delivery tracking.

Only this module talks to Google. Callers depend on the ``RoutingProvider`` and
``GeocodeProvider`` protocols, so the deterministic fallbacks are what the tests
exercise and a missing API key is a configuration state rather than a failure.
"""
import logging
import math
from dataclasses import dataclass
from typing import Protocol

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
        straight = sum(
            haversine_km(a, b) for a, b in zip(waypoints, waypoints[1:])
        )
        distance_km = straight * ROAD_WINDING_FACTOR
        speed = settings.delivery_average_speed_kmh or 25.0
        minutes = math.ceil(distance_km / speed * 60)
        return RouteEstimate(
            distance_km=round(distance_km, 2),
            duration_minutes=max(1, minutes),
            source="estimate",
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/modules/delivery/test_routing.py -q --no-cov`
Expected: 6 passed.

- [ ] **Step 6: Verify nothing else regressed**

Run: `pytest -q --no-cov` then `flake8 src`
Expected: full suite green, flake8 silent.

- [ ] **Step 7: Hand the commit to the human**

Suggested message:

```
feat(delivery): haversine routing provider

Distance and duration with no network call, the fallback the Google
adapter degrades to. Also clears google_maps_api_key in the test
credential fixture so the suite never calls the live API.
```

---

### Task 2: Google Routes adapter with fallback and misconfiguration suppression

**Files:**
- Modify: `src/modules/delivery/providers.py`
- Modify: `tests/modules/delivery/test_routing.py`

**Interfaces:**
- Consumes: `Coordinate`, `RouteEstimate`, `HaversineRouting` from Task 1.
- Produces: `GoogleRoutesProvider(redis=None)`, `routing_provider(redis=None) -> RoutingProvider`, `MAPS_DISABLED_KEY = "delivery:maps_disabled"`, `MAPS_DISABLED_TTL_SECONDS = 600`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/delivery/test_routing.py`. `httpx.MockTransport` is used rather than patching, so the adapter's real request construction is exercised.

```python
import httpx

from src.config import settings
from src.modules.delivery.providers import (
    MAPS_DISABLED_KEY,
    GoogleRoutesProvider,
    routing_provider,
)

OK_BODY = {"routes": [{"distanceMeters": 12005, "duration": "1062s"}]}


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_google_parses_distance_and_duration():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Goog-Api-Key")
        return httpx.Response(200, json=OK_BODY)

    provider = GoogleRoutesProvider(api_key="test-key", transport=_transport(handler))
    estimate = await provider.route([PALERMO, CATANIA])

    assert estimate.distance_km == pytest.approx(12.005)
    assert estimate.duration_minutes == 18  # ceil(1062 / 60)
    assert estimate.source == "google"
    assert "computeRoutes" in seen["url"]
    assert seen["key"] == "test-key"


@pytest.mark.asyncio
async def test_google_sends_intermediate_waypoints():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    mid = Coordinate(latitude=37.8, longitude=14.2)
    provider = GoogleRoutesProvider(api_key="k", transport=_transport(handler))
    await provider.route([PALERMO, mid, CATANIA])

    assert len(seen["body"]["intermediates"]) == 1
    assert seen["body"]["travelMode"] == "DRIVE"


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
async def test_routing_provider_selects_by_configured_key(monkeypatch):
    assert isinstance(routing_provider(), HaversineRouting)
    monkeypatch.setattr(settings, "google_maps_api_key", "configured")
    assert isinstance(routing_provider(), GoogleRoutesProvider)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/modules/delivery/test_routing.py -q --no-cov`
Expected: `ImportError: cannot import name 'GoogleRoutesProvider'`.

- [ ] **Step 3: Write the implementation**

Append to `src/modules/delivery/providers.py`:

```python
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters"
REQUEST_TIMEOUT_SECONDS = 8.0

# Set after a configuration failure (403 / PERMISSION_DENIED). A disabled API,
# revoked key, or lapsed billing returns the same response on every retry, so
# stop asking for a while instead of paying a doomed round trip per ETA.
MAPS_DISABLED_KEY = "delivery:maps_disabled"
MAPS_DISABLED_TTL_SECONDS = 600


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


class _MapsMisconfigured(Exception):
    """A permission failure that retrying cannot fix."""


def routing_provider(redis=None) -> RoutingProvider:
    """Google when a key is configured, haversine otherwise."""
    if settings.google_maps_api_key:
        return GoogleRoutesProvider(settings.google_maps_api_key, redis=redis)
    return HaversineRouting()
```

Add `import httpx` to the imports at the top of the file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/modules/delivery/test_routing.py -q --no-cov`
Expected: 12 passed.

- [ ] **Step 5: Verify the suite and lint**

Run: `pytest -q --no-cov` then `flake8 src`
Expected: green and silent.

- [ ] **Step 6: Hand the commit to the human**

```
feat(delivery): Google Routes adapter with graceful degradation

Parses computeRoutes responses, falls back to the haversine estimate on
transient errors, and suppresses calls for ten minutes after a 403 so a
misconfigured key does not cost a round trip per ETA.
```

---

### Task 3: Geocoding providers

**Files:**
- Modify: `src/modules/delivery/providers.py`
- Create: `tests/modules/delivery/test_geocoding.py`

**Interfaces:**
- Consumes: `Coordinate` from Task 1.
- Produces: `GeocodeProvider` protocol with `async geocode(line1: str, city: str, postal_code: str) -> Coordinate | None`, `NullGeocoder()`, `GoogleGeocoder(api_key, transport=None)`, `geocode_provider() -> GeocodeProvider`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/delivery/test_geocoding.py`:

```python
"""Geocoding providers: the null default and the Google adapter."""
import httpx
import pytest

from src.config import settings
from src.modules.delivery.providers import (
    Coordinate,
    GoogleGeocoder,
    NullGeocoder,
    geocode_provider,
)

OK_BODY = {
    "status": "OK",
    "results": [{"geometry": {"location": {"lat": 37.4224864, "lng": -122.0855962}}}],
}


@pytest.mark.asyncio
async def test_null_geocoder_returns_none():
    assert await NullGeocoder().geocode("1 Main St", "Metropolis", "12345") is None


@pytest.mark.asyncio
async def test_google_geocoder_returns_coordinate():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["address"] = request.url.params.get("address")
        return httpx.Response(200, json=OK_BODY)

    coord = await GoogleGeocoder("k", transport=httpx.MockTransport(handler)).geocode(
        "1600 Amphitheatre Parkway", "Mountain View", "94043"
    )
    assert coord == Coordinate(latitude=37.4224864, longitude=-122.0855962)
    assert "1600 Amphitheatre Parkway" in seen["address"]
    assert "Mountain View" in seen["address"]
    assert "94043" in seen["address"]


@pytest.mark.asyncio
async def test_google_geocoder_returns_none_on_zero_results():
    body = {"status": "ZERO_RESULTS", "results": []}
    coord = await GoogleGeocoder(
        "k", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ).geocode("nowhere", "nocity", "00000")
    assert coord is None


@pytest.mark.asyncio
async def test_google_geocoder_returns_none_on_request_denied():
    body = {"status": "REQUEST_DENIED", "error_message": "API not activated"}
    coord = await GoogleGeocoder(
        "k", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ).geocode("1 Main St", "Metropolis", "12345")
    assert coord is None


@pytest.mark.asyncio
async def test_google_geocoder_returns_none_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    coord = await GoogleGeocoder("k", transport=httpx.MockTransport(handler)).geocode(
        "1 Main St", "Metropolis", "12345"
    )
    assert coord is None


@pytest.mark.asyncio
async def test_geocode_provider_selects_by_configured_key(monkeypatch):
    assert isinstance(geocode_provider(), NullGeocoder)
    monkeypatch.setattr(settings, "google_maps_api_key", "configured")
    assert isinstance(geocode_provider(), GoogleGeocoder)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/modules/delivery/test_geocoding.py -q --no-cov`
Expected: `ImportError: cannot import name 'GoogleGeocoder'`.

- [ ] **Step 3: Write the implementation**

Append to `src/modules/delivery/providers.py`:

```python
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
                logger.info(
                    "Geocoding returned %s for %r", body.get("status"), address
                )
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/modules/delivery/test_geocoding.py -q --no-cov`
Expected: 6 passed.

- [ ] **Step 5: Verify the suite and lint**

Run: `pytest -q --no-cov` then `flake8 src`

- [ ] **Step 6: Hand the commit to the human**

```
feat(delivery): geocoding providers

Google Geocoding adapter plus a null default, both returning None on
failure so an address that will not geocode still saves.
```

---

### Task 4: Address coordinates — model, migration, schema

**Files:**
- Modify: `src/modules/users/models.py:44-61`
- Modify: `src/modules/users/schemas.py:184-195`
- Create: `alembic/versions/0008_address_coordinates.py`
- Create: `tests/modules/users/test_address_geocoding.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Address.latitude: float | None`, `Address.longitude: float | None`, both exposed on `AddressResponse`.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/users/test_address_geocoding.py`:

```python
"""Address coordinates: storage, exposure, and geocode-on-save."""
import pytest


async def _login(api_client, email, phone):
    await api_client.post("/auth/register", json={
        "email": email, "phone": phone, "first_name": "T", "last_name": "U",
        "password": "supersecret1", "role": "customer"})
    token = (await api_client.post(
        "/auth/login", json={"email": email, "password": "supersecret1"}
    )).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_address_response_exposes_nullable_coordinates(api_client):
    headers = await _login(api_client, "coords@x.com", "+15559620001")
    created = await api_client.post("/users/me/addresses", json={
        "label": "home", "line1": "1 Main St", "city": "Metropolis",
        "postal_code": "12345"}, headers=headers)

    assert created.status_code in (200, 201)
    body = created.json()
    # No geocoder is configured in tests, so the address saves ungeocoded.
    assert body["latitude"] is None
    assert body["longitude"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/modules/users/test_address_geocoding.py -q --no-cov`
Expected: `KeyError: 'latitude'`.

- [ ] **Step 3: Add the model columns**

In `src/modules/users/models.py`, add `Float` to the `sqlalchemy` import and add to `Address`, after `is_default`:

```python
    # Nullable: existing addresses have no coordinates, and an address that will
    # not geocode must still save. None means "not mappable", never 0.0.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4: Add the schema fields**

In `src/modules/users/schemas.py`, add to `AddressResponse` after `is_default`:

```python
    latitude: float | None = None
    longitude: float | None = None
```

- [ ] **Step 5: Write the migration**

Create `alembic/versions/0008_address_coordinates.py`:

```python
"""address coordinates

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and additive: every existing address stays valid and reads as
    # "not mappable", which is how they behaved before this column existed.
    op.add_column('addresses', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('addresses', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('addresses', 'longitude')
    op.drop_column('addresses', 'latitude')
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/modules/users/test_address_geocoding.py -q --no-cov`
Expected: 1 passed.

- [ ] **Step 7: Verify the migration and the suite**

Run: `pytest -q --no-cov`, then `flake8 src`, then check the migration is well-formed with `alembic heads` (expect `0008 (head)`). Applying it needs a live Postgres — if one is running, `alembic upgrade head`; otherwise note that the suite builds its schema from the models via `conftest`, so passing tests do not prove the migration runs.

- [ ] **Step 8: Hand the commit to the human**

```
feat(users): nullable coordinates on addresses

Adds latitude/longitude to addresses with migration 0008 and exposes them
on AddressResponse, so a delivery has a routable endpoint.
```

---

### Task 5: Geocode addresses on save

**Files:**
- Modify: `src/modules/users/profile.py:34-43` and `:54-75`
- Modify: `tests/modules/users/test_address_geocoding.py`

**Interfaces:**
- Consumes: `Coordinate`, `GeocodeProvider`, `geocode_provider` (Task 3); `Address.latitude` / `.longitude` (Task 4).
- Produces: `add_address(session, user, data, geocoder=None)` and `update_address(session, user, address_id, data, geocoder=None)` — the optional argument is how tests inject a fake, matching `payments/service.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/users/test_address_geocoding.py`:

```python
from src.modules.delivery.providers import Coordinate
from src.modules.users import profile
from src.modules.users.models import User
from src.modules.users.schemas import AddressCreate, AddressUpdate


class FakeGeocoder:
    """Records every call and returns a fixed point."""

    def __init__(self, result=Coordinate(latitude=12.9716, longitude=77.5946)):
        self.result = result
        self.calls = []

    async def geocode(self, line1, city, postal_code):
        self.calls.append((line1, city, postal_code))
        return self.result


async def _user(db_session):
    user = User(email="geo@x.com", phone="+15559620002", first_name="G",
                last_name="U", hashed_password="x", role="customer")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_add_address_stores_geocoded_coordinates(db_session):
    user = await _user(db_session)
    geocoder = FakeGeocoder()

    address = await profile.add_address(
        db_session, user,
        AddressCreate(line1="1 Main St", city="Bengaluru", postal_code="560001"),
        geocoder=geocoder,
    )

    assert address.latitude == pytest.approx(12.9716)
    assert address.longitude == pytest.approx(77.5946)
    assert geocoder.calls == [("1 Main St", "Bengaluru", "560001")]


@pytest.mark.asyncio
async def test_add_address_saves_when_geocoding_returns_none(db_session):
    user = await _user(db_session)

    address = await profile.add_address(
        db_session, user,
        AddressCreate(line1="nowhere", city="nocity", postal_code="00000"),
        geocoder=FakeGeocoder(result=None),
    )

    assert address.id is not None
    assert address.latitude is None


@pytest.mark.asyncio
async def test_editing_a_location_field_regeocodes(db_session):
    user = await _user(db_session)
    geocoder = FakeGeocoder()
    address = await profile.add_address(
        db_session, user,
        AddressCreate(line1="1 Main St", city="Bengaluru", postal_code="560001"),
        geocoder=geocoder,
    )

    geocoder.result = Coordinate(latitude=13.0, longitude=77.7)
    await profile.update_address(
        db_session, user, address.id, AddressUpdate(line1="2 Other Rd"),
        geocoder=geocoder,
    )

    assert len(geocoder.calls) == 2
    assert geocoder.calls[1] == ("2 Other Rd", "Bengaluru", "560001")
    assert address.latitude == pytest.approx(13.0)


@pytest.mark.asyncio
async def test_editing_only_the_label_does_not_regeocode(db_session):
    user = await _user(db_session)
    geocoder = FakeGeocoder()
    address = await profile.add_address(
        db_session, user,
        AddressCreate(line1="1 Main St", city="Bengaluru", postal_code="560001"),
        geocoder=geocoder,
    )

    await profile.update_address(
        db_session, user, address.id, AddressUpdate(label="work"),
        geocoder=geocoder,
    )

    assert len(geocoder.calls) == 1  # unchanged from the create
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/modules/users/test_address_geocoding.py -q --no-cov`
Expected: `TypeError: add_address() got an unexpected keyword argument 'geocoder'`.

- [ ] **Step 3: Implement geocoding in `profile.py`**

Add the import:

```python
from src.modules.delivery.providers import GeocodeProvider, geocode_provider
```

Add a module-level constant and rewrite the two functions:

```python
# Editing any of these invalidates a stored geocode; editing anything else
# (label, is_default, line2) does not, so it costs no API call.
_LOCATION_FIELDS = ("line1", "city", "postal_code")


async def add_address(
    session: AsyncSession,
    user: User,
    data: AddressCreate,
    geocoder: GeocodeProvider | None = None,
) -> Address:
    """Create an address for the user. Setting it default unsets any other.

    The address is geocoded on the way in when a provider is configured.
    Geocoding never fails the write: an unresolvable address saves with null
    coordinates and simply is not mappable.
    """
    if data.is_default:
        await _clear_default(session, user)

    address = Address(user_id=user.id, **data.model_dump())
    point = await (geocoder or geocode_provider()).geocode(
        data.line1, data.city, data.postal_code
    )
    if point is not None:
        address.latitude = point.latitude
        address.longitude = point.longitude

    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address


async def update_address(
    session: AsyncSession,
    user: User,
    address_id: int,
    data: AddressUpdate,
    geocoder: GeocodeProvider | None = None,
) -> Address:
    """Apply partial edits to an address the user owns; 404 if it is not theirs.

    Promoting an address to default unsets any other, matching ``add_address``.
    Re-geocodes only when the location actually moved.
    """
    address = await _owned_address(session, user, address_id)
    updates = data.model_dump(exclude_unset=True)
    # line2 is the only nullable column, so a null anywhere else means "leave
    # this field alone" rather than "clear it".
    updates = {k: v for k, v in updates.items() if v is not None or k == "line2"}

    if updates.get("is_default"):
        await _clear_default(session, user)

    moved = any(
        field in updates and updates[field] != getattr(address, field)
        for field in _LOCATION_FIELDS
    )

    for field, value in updates.items():
        setattr(address, field, value)

    if moved:
        point = await (geocoder or geocode_provider()).geocode(
            address.line1, address.city, address.postal_code
        )
        address.latitude = point.latitude if point else None
        address.longitude = point.longitude if point else None

    await session.commit()
    await session.refresh(address)
    return address
```

Note the deliberate choice in the `moved` branch: a failed re-geocode **clears** the old coordinates rather than keeping them, because stale coordinates for a new street address would route the driver to the wrong place. Ungeocoded is safer than wrong.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/modules/users/test_address_geocoding.py -q --no-cov`
Expected: 5 passed.

- [ ] **Step 5: Verify the suite and lint**

Run: `pytest -q --no-cov` then `flake8 src`
Expected: green and silent. Existing address tests must still pass — the new argument is optional.

- [ ] **Step 6: Hand the commit to the human**

```
feat(users): geocode addresses on save

Resolves coordinates when an address is created and re-resolves only when
line1, city, or postal_code changes. Geocoding never fails the write; a
failed re-geocode clears stale coordinates rather than routing to the
wrong place.
```

---

### Task 6: ETA assembly and cache

**Files:**
- Create: `src/modules/delivery/eta.py`
- Create: `tests/modules/delivery/test_eta.py`

**Interfaces:**
- Consumes: `Coordinate`, `RouteEstimate`, `RoutingProvider`, `routing_provider` (Tasks 1–2); `Delivery`, `DeliveryStatus` (`src/modules/delivery/models.py`).
- Produces: `waypoints_for(status, driver, restaurant, destination) -> list[Coordinate]`, `estimate_for_order(redis, order_id, waypoints, provider=None) -> RouteEstimate | None`, `invalidate(redis, order_id) -> None`, `cache_key(order_id) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/delivery/test_eta.py`:

```python
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
async def test_estimate_survives_a_missing_redis(fake_redis):
    provider = CountingProvider()
    estimate = await eta.estimate_for_order(None, 1, [DRIVER, DESTINATION], provider=provider)
    assert estimate is not None
    assert provider.calls == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/modules/delivery/test_eta.py -q --no-cov`
Expected: `ModuleNotFoundError: No module named 'src.modules.delivery.eta'`.

- [ ] **Step 3: Write the implementation**

Create `src/modules/delivery/eta.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/modules/delivery/test_eta.py -q --no-cov`
Expected: 9 passed.

- [ ] **Step 5: Verify the suite and lint**

Run: `pytest -q --no-cov` then `flake8 src`

- [ ] **Step 6: Hand the commit to the human**

```
feat(delivery): ETA assembly with a per-order cache

Selects the remaining legs by delivery status, caches the route estimate
in Redis for the configured TTL, and invalidates on demand. Driver
position stays uncached so the marker still moves at poll granularity.
```

---

### Task 7: Enriched tracking payload

**Files:**
- Modify: `src/modules/delivery/schemas.py`
- Modify: `src/modules/delivery/service.py:159-169` and the four action functions
- Modify: `src/modules/delivery/router.py:74-81`
- Modify: `tests/modules/delivery/test_location.py:79`
- Modify: `frontend/src/api/delivery.ts`
- Modify: `tests/modules/delivery/test_api.py`

**Interfaces:**
- Consumes: `waypoints_for`, `estimate_for_order`, `invalidate` (Task 6); `Address.latitude` / `.longitude` (Task 4).
- Produces: `CoordinateRead`, `TrackingRead` (both in `delivery/schemas.py`); `tracking_for_order` returning `TrackingRead`; frontend `Tracking` interface with `driver`, `restaurant`, `destination`, `eta_minutes`, `distance_km`, `eta_source`.

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/delivery/test_api.py` (reuse the `_login` helper already in that file; if its signature differs, copy the one from `test_location.py`):

```python
@pytest.mark.asyncio
async def test_tracking_includes_coordinates_and_eta(api_client):
    """A picked-up order reports driver, destination, and an estimated ETA."""
    owner = await _login(api_client, "restaurant", "trk-o@x.com", "+15559630001")
    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00",
        "latitude": 12.9352, "longitude": 77.6245}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories",
        json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"},
        headers=owner)).json()

    driver = await _login(api_client, "driver", "trk-d@x.com", "+15559630002")
    await api_client.post("/delivery/location",
        json={"latitude": 12.9716, "longitude": 77.5946}, headers=driver)

    cust = await _login(api_client, "customer", "trk-c@x.com", "+15559630003")
    await api_client.post("/cart/items",
        json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis",
        "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr["id"], "price_hash": ph}, headers=cust)).json()["id"]

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)

    body = (await api_client.get(f"/delivery/orders/{oid}/tracking", headers=cust)).json()

    assert body["driver"]["latitude"] == pytest.approx(12.9716, abs=1e-3)
    assert body["restaurant"]["latitude"] == pytest.approx(12.9352, abs=1e-3)
    # The test address is not geocodable and no geocoder is configured, so the
    # destination is unknown and the ETA covers driver -> restaurant only.
    assert body["destination"] is None
    assert body["eta_minutes"] is not None
    assert body["eta_source"] == "estimate"
    assert body["distance_km"] > 0
```

Also change `tests/modules/delivery/test_location.py:79` from `assert body["location"] is not None` to `assert body["driver"] is not None`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/modules/delivery -q --no-cov`
Expected: the new test fails on `KeyError: 'driver'`, and `test_location.py` fails on the renamed key.

- [ ] **Step 3: Add the schemas**

Append to `src/modules/delivery/schemas.py`:

```python
class CoordinateRead(BaseModel):
    latitude: float
    longitude: float


class TrackingRead(BaseModel):
    """Everything the customer's tracking view needs, in one poll.

    Every geographic field is optional. A driver who has not shared a position,
    an ungeocoded address, or a restaurant without coordinates each yield null
    and a null ETA — states the UI renders honestly rather than faking.
    """

    order_id: int
    status: str
    driver_id: int | None
    driver: CoordinateRead | None = None
    restaurant: CoordinateRead | None = None
    destination: CoordinateRead | None = None
    eta_minutes: int | None = None
    distance_km: float | None = None
    eta_source: str | None = None  # "google" | "estimate" | None
```

- [ ] **Step 4: Rewrite `tracking_for_order`**

In `src/modules/delivery/service.py`, add the imports:

```python
from src.modules.delivery import eta as eta_module
from src.modules.delivery.providers import Coordinate
from src.modules.delivery.schemas import TrackingRead
from src.modules.users.models import Address
```

Replace `tracking_for_order` with:

```python
def _coord(obj) -> Coordinate | None:
    """A Coordinate from anything carrying latitude/longitude, or None."""
    if obj is None or obj.latitude is None or obj.longitude is None:
        return None
    return Coordinate(latitude=obj.latitude, longitude=obj.longitude)


async def tracking_for_order(session: AsyncSession, user, redis, order_id: int) -> TrackingRead:
    """Delivery status, live driver position, and the ETA for an order.

    Access follows the order's visibility rules (customer / restaurant / admin).
    """
    order = await order_service.get_order_for_user(session, user, order_id)  # 403/404
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery is None:
        raise NotFoundException("Delivery", str(order_id))

    driver_point = None
    if delivery.driver_id is not None and redis is not None:
        raw = await location.get_location(redis, delivery.driver_id)
        if raw is not None:
            driver_point = Coordinate(latitude=raw["latitude"], longitude=raw["longitude"])

    restaurant_point = _coord(await session.get(Restaurant, order.restaurant_id))
    destination_point = _coord(await session.get(Address, order.address_id))

    waypoints = eta_module.waypoints_for(
        delivery.status, driver_point, restaurant_point, destination_point
    )
    estimate = await eta_module.estimate_for_order(redis, order_id, waypoints)

    return TrackingRead(
        order_id=order_id,
        status=delivery.status,
        driver_id=delivery.driver_id,
        driver=driver_point,
        restaurant=restaurant_point,
        destination=destination_point,
        eta_minutes=estimate.duration_minutes if estimate else None,
        distance_km=estimate.distance_km if estimate else None,
        eta_source=estimate.source if estimate else None,
    )
```

`Coordinate` is a frozen dataclass and `CoordinateRead` is a Pydantic model with the same two fields, so passing the dataclass straight in works — Pydantic reads the attributes. If validation complains, add `model_config = ConfigDict(from_attributes=True)` to `CoordinateRead`.

- [ ] **Step 5: Invalidate the cache on every status change**

Still in `service.py`, thread `redis` through the four action functions and invalidate. `reject_assignment` already takes `redis`; add `redis=None` to the other three:

```python
async def accept_assignment(session: AsyncSession, driver: User, order_id: int, redis=None) -> Delivery:
```

and immediately before each `return delivery`, add:

```python
    await eta_module.invalidate(redis, order_id)
```

Do this in `accept_assignment`, `reject_assignment`, `pickup`, and `deliver`. The `pickup` case matters most: it flips the route from three legs to two.

- [ ] **Step 6: Pass `redis` from the router**

In `src/modules/delivery/router.py`, add `response_model=TrackingRead` to the tracking route, import `TrackingRead` from the schemas, and add `redis=Depends(get_redis)` to the `accept`, `pickup`, and `deliver` handlers, forwarding it to the service call. For example:

```python
@router.post("/orders/{order_id}/pickup", response_model=DeliveryRead)
async def pickup(order_id: int, driver: User = Depends(_driver),
                 session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.pickup(session, driver, order_id, redis=redis)
```

- [ ] **Step 7: Update the frontend types**

In `frontend/src/api/delivery.ts`, replace the `Tracking` interface:

```typescript
export interface Coordinate {
  latitude: number
  longitude: number
}

export interface Tracking {
  order_id: number
  status: string
  driver_id: number | null
  driver: Coordinate | null
  restaurant: Coordinate | null
  destination: Coordinate | null
  eta_minutes: number | null
  distance_km: number | null
  eta_source: 'google' | 'estimate' | null
}
```

Then fix the one consumer: in `frontend/src/pages/OrderDetailPage.tsx:169-172`, `tracking.location` becomes `tracking.driver`. This is a placeholder edit — Task 10 replaces that block entirely.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/modules/delivery -q --no-cov`
Expected: all pass, including the renamed assertion.

- [ ] **Step 9: Verify everything**

Run: `pytest -q --no-cov`, `flake8 src`, then `cd frontend && npm run build`
Expected: green, silent, and a clean typecheck.

- [ ] **Step 10: Hand the commit to the human**

```
feat(delivery): coordinates and ETA in the tracking payload

Replaces the bare dict with TrackingRead, carrying driver, restaurant,
and destination points plus eta_minutes, distance_km, and eta_source.
Renames location to driver, and invalidates the cached ETA on every
delivery status change.
```

---

### Task 8: `useDriverLocation` hook

**Files:**
- Create: `frontend/src/lib/useDriverLocation.ts`
- Create: `frontend/tests/lib/useDriverLocation.test.ts`

**Interfaces:**
- Consumes: `deliveryApi` from `frontend/src/api/delivery.ts`.
- Produces: `useDriverLocation()` returning `{ sharing: boolean, status: DriverLocationStatus, lastUpdate: number | null, error: string | null, enable(): Promise<void>, disable(): Promise<void> }`, where `DriverLocationStatus` is `'off' | 'sharing' | 'denied' | 'unavailable' | 'unsupported'`. Also `SHARE_STORAGE_KEY`, `MIN_INTERVAL_MS = 10_000`, `MIN_DISTANCE_M = 25`.

- [ ] **Step 1: Add the API binding**

In `frontend/src/api/delivery.ts`, add to `deliveryApi`:

```typescript
  setOnline: (online: boolean) =>
    request<{ driver_id: number; online: boolean }>('/delivery/status', {
      method: 'POST', auth: true, body: { online },
    }),
  postLocation: (latitude: number, longitude: number) =>
    request<{ driver_id: number }>('/delivery/location', {
      method: 'POST', auth: true, body: { latitude, longitude },
    }),
```

Check how `request` takes a body in `frontend/src/api/client.ts` and match it — other modules already POST JSON, so copy the shape from `ordersApi` rather than inventing one.

- [ ] **Step 2: Write the failing tests**

Create `frontend/tests/lib/useDriverLocation.test.ts`:

```typescript
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deliveryApi } from '../../src/api/delivery'
import { useDriverLocation } from '../../src/lib/useDriverLocation'

type WatchCallback = (position: { coords: { latitude: number; longitude: number } }) => void

let watchCallback: WatchCallback | null = null
let errorCallback: ((e: { code: number; message: string }) => void) | null = null

function mockGeolocation() {
  watchCallback = null
  errorCallback = null
  const geolocation = {
    watchPosition: vi.fn((onSuccess: WatchCallback, onError) => {
      watchCallback = onSuccess
      errorCallback = onError
      return 1
    }),
    clearWatch: vi.fn(),
  }
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: geolocation, configurable: true, writable: true,
  })
  return geolocation
}

function emit(latitude: number, longitude: number) {
  act(() => { watchCallback?.({ coords: { latitude, longitude } }) })
}

describe('useDriverLocation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    vi.spyOn(deliveryApi, 'setOnline').mockResolvedValue({ driver_id: 1, online: true })
    vi.spyOn(deliveryApi, 'postLocation').mockResolvedValue({ driver_id: 1 })
  })

  it('starts off and posts nothing', () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    expect(result.current.sharing).toBe(false)
    expect(result.current.status).toBe('off')
    expect(deliveryApi.postLocation).not.toHaveBeenCalled()
  })

  it('going online marks the driver available then posts the position', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())

    await act(async () => { await result.current.enable() })
    expect(deliveryApi.setOnline).toHaveBeenCalledWith(true)

    emit(12.9716, 77.5946)
    await waitFor(() => expect(deliveryApi.postLocation).toHaveBeenCalledWith(12.9716, 77.5946))
    expect(result.current.status).toBe('sharing')
  })

  it('suppresses an update that has barely moved', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => { await result.current.enable() })

    emit(12.9716, 77.5946)
    await waitFor(() => expect(deliveryApi.postLocation).toHaveBeenCalledTimes(1))
    emit(12.97161, 77.59461) // ~1.5 m later, well inside both thresholds
    expect(deliveryApi.postLocation).toHaveBeenCalledTimes(1)
  })

  it('reports a denied permission and posts nothing', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => { await result.current.enable() })

    act(() => { errorCallback?.({ code: 1, message: 'denied' }) })
    await waitFor(() => expect(result.current.status).toBe('denied'))
    expect(deliveryApi.postLocation).not.toHaveBeenCalled()
  })

  it('going offline clears the watch and marks the driver unavailable', async () => {
    const geolocation = mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => { await result.current.enable() })
    await act(async () => { await result.current.disable() })

    expect(deliveryApi.setOnline).toHaveBeenLastCalledWith(false)
    expect(geolocation.clearWatch).toHaveBeenCalled()
    expect(result.current.status).toBe('off')
  })

  it('reports unsupported when the browser has no geolocation', () => {
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: undefined, configurable: true, writable: true,
    })
    const { result } = renderHook(() => useDriverLocation())
    expect(result.current.status).toBe('unsupported')
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run tests/lib/useDriverLocation.test.ts`
Expected: cannot resolve `../../src/lib/useDriverLocation`.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/useDriverLocation.ts`:

```typescript
// Publishes the driver's position while they choose to share it.
//
// Sharing is opt-in and off by default: a page that tracked someone's position
// because they happened to have an active delivery would be tracking without
// consent. The choice is persisted so a mid-shift refresh does not silently
// stop sharing.
import { useCallback, useEffect, useRef, useState } from 'react'

import { deliveryApi } from '../api/delivery'

export type DriverLocationStatus =
  | 'off'
  | 'sharing'
  | 'denied'
  | 'unavailable'
  | 'unsupported'

export const SHARE_STORAGE_KEY = 'delivery.shareLocation'
// watchPosition fires far more often than the server needs. Post at most once
// per interval, and only when the driver has actually moved.
export const MIN_INTERVAL_MS = 10_000
export const MIN_DISTANCE_M = 25

const EARTH_RADIUS_M = 6_371_000

function metresBetween(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.latitude - a.latitude)
  const dLon = toRad(b.longitude - a.longitude)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h))
}

export function useDriverLocation() {
  const supported = typeof navigator !== 'undefined' && !!navigator.geolocation
  const [sharing, setSharing] = useState(false)
  const [status, setStatus] = useState<DriverLocationStatus>(
    supported ? 'off' : 'unsupported',
  )
  const [lastUpdate, setLastUpdate] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const watchId = useRef<number | null>(null)
  const lastSent = useRef<{ at: number; latitude: number; longitude: number } | null>(null)

  const stopWatch = useCallback(() => {
    if (watchId.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId.current)
    }
    watchId.current = null
    lastSent.current = null
  }, [])

  const startWatch = useCallback(() => {
    if (!navigator.geolocation || watchId.current !== null) return
    watchId.current = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        const previous = lastSent.current
        const now = Date.now()
        if (
          previous &&
          now - previous.at < MIN_INTERVAL_MS &&
          metresBetween(previous, { latitude, longitude }) < MIN_DISTANCE_M
        ) {
          return
        }
        lastSent.current = { at: now, latitude, longitude }
        void deliveryApi
          .postLocation(latitude, longitude)
          .then(() => {
            setLastUpdate(now)
            setStatus('sharing')
            setError(null)
          })
          .catch(() => setError('Could not reach the server with your location.'))
      },
      (positionError) => {
        // 1 = PERMISSION_DENIED in the Geolocation API.
        setStatus(positionError.code === 1 ? 'denied' : 'unavailable')
        setError(
          positionError.code === 1
            ? 'Location permission is blocked. Enable it in your browser to share your position.'
            : 'Your position is unavailable right now.',
        )
      },
      { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
    )
  }, [])

  const enable = useCallback(async () => {
    setError(null)
    setSharing(true)
    localStorage.setItem(SHARE_STORAGE_KEY, 'true')
    try {
      await deliveryApi.setOnline(true)
    } catch {
      setError('Could not mark you online.')
    }
    setStatus('sharing')
    startWatch()
  }, [startWatch])

  const disable = useCallback(async () => {
    stopWatch()
    setSharing(false)
    setStatus(supported ? 'off' : 'unsupported')
    setLastUpdate(null)
    localStorage.setItem(SHARE_STORAGE_KEY, 'false')
    try {
      await deliveryApi.setOnline(false)
    } catch {
      setError('Could not mark you offline.')
    }
  }, [stopWatch, supported])

  // Resume sharing after a refresh if that is where the driver left it.
  useEffect(() => {
    if (supported && localStorage.getItem(SHARE_STORAGE_KEY) === 'true') {
      void enable()
    }
    return stopWatch
    // Intentionally once on mount: re-running would restart the watch on
    // every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { sharing, status, lastUpdate, error, enable, disable }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/lib/useDriverLocation.test.ts`
Expected: 6 passed.

- [ ] **Step 6: Verify the whole frontend**

Run: `cd frontend && npm test` then `npm run build`
Expected: all suites pass, clean typecheck.

- [ ] **Step 7: Hand the commit to the human**

```
feat(frontend): useDriverLocation hook

Opt-in geolocation watch that posts the driver's position at most every
ten seconds and only after 25 metres of movement, with explicit denied,
unavailable, and unsupported states.
```

---

### Task 9: Driver share-location toggle and next-stop link

**Files:**
- Modify: `src/modules/delivery/schemas.py`
- Modify: `src/modules/delivery/service.py` (`list_for_driver`)
- Modify: `tests/modules/delivery/test_api.py`
- Modify: `frontend/src/api/delivery.ts`
- Modify: `frontend/src/pages/DriverPage.tsx`
- Create: `frontend/tests/pages/DriverPage.test.tsx`
- Modify: `frontend/src/layout.css`

**Interfaces:**
- Consumes: `useDriverLocation` (Task 8), `deliveryApi` and `CoordinateRead` (Task 7).
- Produces: `DeliveryRead.restaurant` / `DeliveryRead.destination` (both `CoordinateRead | None`); frontend `Delivery` gaining the same two fields.

**Why the backend changes here:** the driver cannot use the tracking endpoint.
`tracking_for_order` calls `get_order_for_user`, which admits the customer, the
owning restaurant, and admins — a driver hits `ForbiddenException`. Rather than
widening that endpoint's access, the coordinates the driver needs ride along on
the assignments list they already fetch. Narrower change, and no new way to read
a customer's address.

- [ ] **Step 1: Write the failing backend test**

Append to `tests/modules/delivery/test_api.py`:

```python
@pytest.mark.asyncio
async def test_assignments_carry_next_stop_coordinates(api_client):
    """A driver's assignment includes the restaurant point for navigation."""
    owner = await _login(api_client, "restaurant", "nav-o@x.com", "+15559640001")
    rid = (await api_client.post("/restaurants", json={
        "name": "P", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000000", "min_order_amount": "5.00",
        "latitude": 12.9352, "longitude": 77.6245}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories",
        json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"},
        headers=owner)).json()

    driver = await _login(api_client, "driver", "nav-d@x.com", "+15559640002")
    await api_client.post("/delivery/location",
        json={"latitude": 12.9716, "longitude": 77.5946}, headers=driver)

    cust = await _login(api_client, "customer", "nav-c@x.com", "+15559640003")
    await api_client.post("/cart/items",
        json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses", json={
        "label": "h", "line1": "1", "city": "Metropolis",
        "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    oid = (await api_client.post("/orders/checkout",
        json={"address_id": addr["id"], "price_hash": ph}, headers=cust)).json()["id"]

    await api_client.post(f"/orders/{oid}/accept", headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "PREPARING"}, headers=owner)
    await api_client.post(f"/orders/{oid}/status", json={"to": "READY_FOR_PICKUP"}, headers=owner)

    assignments = (await api_client.get("/delivery/assignments", headers=driver)).json()
    mine = next(a for a in assignments if a["order_id"] == oid)

    assert mine["restaurant"]["latitude"] == pytest.approx(12.9352, abs=1e-3)
    # The test address is not geocodable, so the destination is unknown.
    assert mine["destination"] is None


@pytest.mark.asyncio
async def test_driver_cannot_read_the_tracking_endpoint(api_client):
    """Tracking is customer/owner/admin only; drivers use their assignments."""
    owner = await _login(api_client, "restaurant", "den-o@x.com", "+15559640004")
    other = await _login(api_client, "driver", "den-d@x.com", "+15559640005")
    rid = (await api_client.post("/restaurants", json={
        "name": "P2", "city": "Metropolis", "address_line": "1",
        "phone": "+15550000001", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    assert rid  # restaurant exists; no order for this driver
    assert (await api_client.get("/delivery/orders/999999/tracking", headers=other)).status_code in (403, 404)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/modules/delivery/test_api.py -q --no-cov`
Expected: `KeyError: 'restaurant'`.

- [ ] **Step 3: Extend the schema**

In `src/modules/delivery/schemas.py`, add to `DeliveryRead` (after `delivered_at`):

```python
    # Where the driver is headed next, for navigation. Null when the restaurant
    # has no coordinates or the customer's address never geocoded.
    restaurant: CoordinateRead | None = None
    destination: CoordinateRead | None = None
```

`CoordinateRead` is defined in this same file by Task 7, so no import is needed.
`DeliveryRead` already sets `model_config = ConfigDict(from_attributes=True)`,
which is what lets the next step's transient attributes be read.

- [ ] **Step 4: Attach the coordinates in `list_for_driver`**

In `src/modules/delivery/service.py`, replace `list_for_driver`. This follows the
same transient-attribute pattern `restaurants/service.py` uses for ratings —
set attributes the response schema reads, rather than returning dicts.

```python
async def list_for_driver(session: AsyncSession, driver_id: int) -> list[Delivery]:
    """A driver's active deliveries, each carrying its next-stop coordinates.

    The driver cannot call the tracking endpoint (that is customer/owner/admin
    only), so the points they need for navigation ride along here.
    """
    from src.modules.orders.models import Order  # local import to avoid cycles

    stmt = (
        select(Delivery)
        .where(Delivery.driver_id == driver_id, Delivery.status.in_(_ACTIVE))
        .order_by(Delivery.id)
    )
    deliveries = list(await session.scalars(stmt))

    for delivery in deliveries:
        order = await session.get(Order, delivery.order_id)
        delivery.restaurant = (
            _coord(await session.get(Restaurant, order.restaurant_id)) if order else None
        )
        delivery.destination = (
            _coord(await session.get(Address, order.address_id)) if order else None
        )
    return deliveries
```

`_coord`, `Restaurant`, and `Address` all arrived with Task 7.

- [ ] **Step 5: Run the backend test to verify it passes**

Run: `pytest tests/modules/delivery -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Extend the frontend type**

In `frontend/src/api/delivery.ts`, add to the `Delivery` interface:

```typescript
  restaurant: Coordinate | null
  destination: Coordinate | null
```

- [ ] **Step 7: Write the failing frontend tests**

Create `frontend/tests/pages/DriverPage.test.tsx`. Check `frontend/tests/pages/OrdersPage.test.tsx` for how it wraps a page in the auth and router providers, and copy that harness exactly rather than inventing one.

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deliveryApi } from '../../src/api/delivery'
import { DriverPage } from '../../src/pages/DriverPage'
// Use the same provider wrapper as OrdersPage.test.tsx.
import { renderWithProviders } from './testHarness'

describe('DriverPage location sharing', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: { watchPosition: vi.fn(() => 1), clearWatch: vi.fn() },
      configurable: true, writable: true,
    })
    vi.spyOn(deliveryApi, 'assignments').mockResolvedValue([
      { id: 1, order_id: 77, driver_id: 3, status: 'ACCEPTED',
        assigned_at: null, picked_up_at: null, delivered_at: null,
        restaurant: { latitude: 12.9352, longitude: 77.6245 },
        destination: { latitude: 12.9, longitude: 77.6 } },
    ])
    vi.spyOn(deliveryApi, 'setOnline').mockResolvedValue({ driver_id: 3, online: true })
    vi.spyOn(deliveryApi, 'postLocation').mockResolvedValue({ driver_id: 3 })
  })

  it('offers sharing as off by default', async () => {
    renderWithProviders(<DriverPage />, { role: 'driver' })
    const toggle = await screen.findByRole('switch', { name: /share my location/i })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(deliveryApi.setOnline).not.toHaveBeenCalled()
  })

  it('turning it on marks the driver online', async () => {
    renderWithProviders(<DriverPage />, { role: 'driver' })
    await userEvent.click(await screen.findByRole('switch', { name: /share my location/i }))
    await waitFor(() => expect(deliveryApi.setOnline).toHaveBeenCalledWith(true))
    expect(await screen.findByText(/sharing your location/i)).toBeInTheDocument()
  })

  it('explains a blocked permission instead of failing silently', async () => {
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: {
        watchPosition: vi.fn((_ok, onError) => { onError({ code: 1, message: 'denied' }); return 1 }),
        clearWatch: vi.fn(),
      },
      configurable: true, writable: true,
    })
    renderWithProviders(<DriverPage />, { role: 'driver' })
    await userEvent.click(await screen.findByRole('switch', { name: /share my location/i }))
    expect(await screen.findByText(/location permission is blocked/i)).toBeInTheDocument()
  })

  it('links to the next stop in Google Maps', async () => {
    renderWithProviders(<DriverPage />, { role: 'driver' })
    const link = await screen.findByRole('link', { name: /navigate/i })
    // ACCEPTED means the food is not aboard yet, so the next stop is the
    // restaurant, not the customer.
    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining('destination=12.9352,77.6245'),
    )
  })

  it('points at the customer once the order is picked up', async () => {
    vi.spyOn(deliveryApi, 'assignments').mockResolvedValue([
      { id: 1, order_id: 77, driver_id: 3, status: 'PICKED_UP',
        assigned_at: null, picked_up_at: null, delivered_at: null,
        restaurant: { latitude: 12.9352, longitude: 77.6245 },
        destination: { latitude: 12.9, longitude: 77.6 } },
    ])
    renderWithProviders(<DriverPage />, { role: 'driver' })
    const link = await screen.findByRole('link', { name: /navigate/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('destination=12.9,77.6'))
  })

  it('omits the link when no coordinate is known', async () => {
    vi.spyOn(deliveryApi, 'assignments').mockResolvedValue([
      { id: 1, order_id: 77, driver_id: 3, status: 'ACCEPTED',
        assigned_at: null, picked_up_at: null, delivered_at: null,
        restaurant: null, destination: null },
    ])
    renderWithProviders(<DriverPage />, { role: 'driver' })
    await screen.findByText(/order #77/i)
    expect(screen.queryByRole('link', { name: /navigate/i })).not.toBeInTheDocument()
  })
})
```

If `frontend/tests/pages/` has no shared harness, write `renderWithProviders` in this file using whatever `OrdersPage.test.tsx` does, rather than adding a new shared module.

- [ ] **Step 8: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run tests/pages/DriverPage.test.tsx`
Expected: no element with role `switch`.

- [ ] **Step 9: Implement the toggle and the next-stop link**

In `frontend/src/pages/DriverPage.tsx`, import the hook and add the panel above the assignment list:

```tsx
import { useDriverLocation } from '../lib/useDriverLocation'

const STATUS_TEXT: Record<string, string> = {
  off: 'Not sharing. Turn this on to receive nearby orders.',
  sharing: 'Sharing your location',
  denied: 'Location permission is blocked. Enable it in your browser to share your position.',
  unavailable: 'Your position is unavailable right now.',
  unsupported: 'This device cannot share a location.',
}
```

Inside the component:

```tsx
  const share = useDriverLocation()
```

And in the returned markup, directly after the `owner-head` div:

```tsx
      <div className="share-card">
        <button
          type="button"
          role="switch"
          aria-checked={share.sharing}
          aria-label="Share my location"
          className="share-switch"
          data-on={share.sharing}
          disabled={share.status === 'unsupported'}
          onClick={() => (share.sharing ? void share.disable() : void share.enable())}
        >
          <span className="share-knob" aria-hidden />
        </button>
        <div>
          <div className="menu-item-name">Share my location</div>
          <div className="muted">
            {STATUS_TEXT[share.status]}
            {share.lastUpdate
              ? ` · updated ${new Date(share.lastUpdate).toLocaleTimeString()}`
              : ''}
          </div>
        </div>
      </div>

      {share.error && <Alert>{share.error}</Alert>}
```

Add a next-stop helper above the component. Before pickup the driver is headed
to the restaurant; once the food is aboard, to the customer:

```tsx
import type { Delivery } from '../api/delivery'

function nextStop(d: Delivery) {
  return d.status === 'PICKED_UP' ? d.destination : d.restaurant
}

function navigateUrl(point: { latitude: number; longitude: number }) {
  // A plain maps URL — no API key, no SDK, and it opens the native app on a
  // phone rather than a web map.
  return `https://www.google.com/maps/dir/?api=1&destination=${point.latitude},${point.longitude}`
}
```

Then render the link inside each delivery card's `delivery-actions` block, before
the existing buttons:

```tsx
                {nextStop(d) && (
                  <a
                    className="link-inline"
                    href={navigateUrl(nextStop(d)!)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Navigate
                  </a>
                )}
```

The link is absent rather than dead when no coordinate is known — a
`destination=null,null` URL would open a broken map.

- [ ] **Step 10: Add the styles**

Append to `frontend/src/layout.css`, matching the existing card conventions in that file:

```css
/* Driver location sharing */
.share-card {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  padding: 0.9rem 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  margin-bottom: 1rem;
}

.share-switch {
  flex: 0 0 auto;
  width: 44px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface-2);
  position: relative;
  cursor: pointer;
  transition: background 150ms ease;
}

.share-switch[data-on='true'] { background: var(--brand); }
.share-switch:disabled { opacity: 0.5; cursor: not-allowed; }

.share-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 150ms ease;
}

.share-switch[data-on='true'] .share-knob { transform: translateX(18px); }
```

Check the actual custom property names at the top of `frontend/src/index.css` and use those — `--line`, `--surface-2`, and `--brand` are placeholders for whatever that file defines.

- [ ] **Step 11: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/pages/DriverPage.test.tsx`
Expected: 6 passed.

- [ ] **Step 12: Verify both stacks**

Run: `pytest -q --no-cov`, `flake8 src`, `cd frontend && npm test`, then `npm run build`

- [ ] **Step 13: Hand the commit to the human**

```
feat(delivery): driver share-location toggle and next-stop navigation

An opt-in switch on the driver page that marks the driver online and
publishes their position, with the blocked, unavailable, and unsupported
cases spelled out rather than failing silently. Assignments now carry the
next-stop coordinates, since the tracking endpoint is closed to drivers.
```

---

### Task 10: `DeliveryMap` — text fallback path

**Files:**
- Create: `frontend/src/components/DeliveryMap.tsx`
- Create: `frontend/tests/components/DeliveryMap.test.tsx`
- Modify: `frontend/src/pages/OrderDetailPage.tsx:163-175`
- Modify: `frontend/src/layout.css`

**Interfaces:**
- Consumes: `Tracking`, `Coordinate` (Task 7).
- Produces: `DeliveryMap({ tracking }: { tracking: Tracking })`, `etaLabel(tracking) -> string`, `mapsKey() -> string | undefined`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/components/DeliveryMap.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DeliveryMap } from '../../src/components/DeliveryMap'
import type { Tracking } from '../../src/api/delivery'

const base: Tracking = {
  order_id: 1,
  status: 'PICKED_UP',
  driver_id: 3,
  driver: { latitude: 12.9716, longitude: 77.5946 },
  restaurant: { latitude: 12.9352, longitude: 77.6245 },
  destination: { latitude: 12.9, longitude: 77.6 },
  eta_minutes: 12,
  distance_km: 3.4,
  eta_source: 'estimate',
}

describe('DeliveryMap without a maps key', () => {
  // frontend/.env carries a real key and Vite exposes it to Vitest, so the
  // unkeyed path has to be stubbed explicitly — otherwise these tests would
  // silently exercise the map branch instead of the fallback.
  beforeEach(() => {
    vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows the ETA and distance as text', () => {
    render(<DeliveryMap tracking={base} />)
    expect(screen.getByText(/12 min/)).toBeInTheDocument()
    expect(screen.getByText(/3\.4 km/)).toBeInTheDocument()
  })

  it('marks a fallback ETA as estimated', () => {
    render(<DeliveryMap tracking={base} />)
    expect(screen.getByText(/estimated/i)).toBeInTheDocument()
  })

  it('does not hedge a Google ETA', () => {
    render(<DeliveryMap tracking={{ ...base, eta_source: 'google' }} />)
    expect(screen.queryByText(/estimated/i)).not.toBeInTheDocument()
  })

  it('says it is still locating when the driver has no position', () => {
    render(<DeliveryMap tracking={{ ...base, driver: null, eta_minutes: null, distance_km: null, eta_source: null }} />)
    expect(screen.getByText(/locating your driver/i)).toBeInTheDocument()
  })

  it('omits the ETA line when no ETA could be computed', () => {
    render(<DeliveryMap tracking={{ ...base, eta_minutes: null, distance_km: null, eta_source: null }} />)
    expect(screen.queryByText(/min/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run tests/components/DeliveryMap.test.tsx`
Expected: cannot resolve `../../src/components/DeliveryMap`.

- [ ] **Step 3: Write the fallback implementation**

Create `frontend/src/components/DeliveryMap.tsx`:

```tsx
// Live delivery tracking. Renders a Google map when a browser key is
// configured and a text panel when it is not — the ETA comes from the server
// either way, so the information is identical and only the presentation drops.
import type { Tracking } from '../api/delivery'

export function mapsKey(): string | undefined {
  return import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
}

export function etaLabel(tracking: Tracking): string | null {
  if (tracking.eta_minutes === null) return null
  const distance =
    tracking.distance_km !== null ? ` · ${tracking.distance_km.toFixed(1)} km away` : ''
  // "estimated" is the honest word for the haversine fallback. A Google ETA
  // accounts for traffic and does not need the hedge.
  const hedge = tracking.eta_source === 'estimate' ? ' (estimated)' : ''
  return `Arriving in ~${tracking.eta_minutes} min${distance}${hedge}`
}

export function DeliveryMap({ tracking }: { tracking: Tracking }) {
  const eta = etaLabel(tracking)

  return (
    <div className="track-card">
      <span className="track-pulse" aria-hidden />
      <div className="track-body">
        <div className="menu-item-name">Out for delivery</div>
        {tracking.driver ? (
          <div className="muted">{eta ?? 'On the way to you'}</div>
        ) : (
          <div className="muted">Locating your driver…</div>
        )}
        {tracking.destination && (
          <a
            className="link-inline"
            href={`https://www.google.com/maps/dir/?api=1&destination=${tracking.destination.latitude},${tracking.destination.longitude}`}
            target="_blank"
            rel="noreferrer"
          >
            Open route in Google Maps
          </a>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Wire it into the order page**

In `frontend/src/pages/OrderDetailPage.tsx`, replace the whole `{tracking && ( … )}` block at lines 163-175 with:

```tsx
      {tracking && <DeliveryMap tracking={tracking} />}
```

and add `import { DeliveryMap } from '../components/DeliveryMap'`.

- [ ] **Step 5: Add the one new style**

Append to `frontend/src/layout.css`:

```css
.track-body { display: grid; gap: 0.25rem; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/components/DeliveryMap.test.tsx`
Expected: 5 passed.

- [ ] **Step 7: Verify the whole frontend**

Run: `cd frontend && npm test` then `npm run build`

- [ ] **Step 8: Hand the commit to the human**

```
feat(frontend): DeliveryMap with a text tracking panel

Replaces the raw coordinate readout with a server-computed ETA and
distance, marked "estimated" only when the fallback provider produced it,
plus a Google Maps route link.
```

---

### Task 11: `DeliveryMap` — the actual map

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/components/DeliveryMap.tsx`
- Modify: `frontend/tests/components/DeliveryMap.test.tsx`
- Modify: `frontend/src/layout.css`

**Interfaces:**
- Consumes: everything from Task 10.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Install the map library**

Run: `cd frontend && npm install @googlemaps/js-api-loader`

> **Changed during execution.** This step originally installed
> `@vis.gl/react-google-maps`. That package cannot be installed here: npm dies
> while extracting its tarball and emits no diagnostic beyond the log path,
> reproducibly across three attempts (cache cleared, correct directory, sandbox
> disabled). `@googlemaps/js-api-loader` is Google's own loader, installs in two
> packages, and carries `@types/google.maps`. The React lifecycle the wrapper
> would have handled is written by hand in `useTrackingMap` — about 40 lines.
>
> Two environment notes for whoever runs this next, both cost real debugging
> time otherwise:
> - `npx` and `npm run` are unreliable on this machine and can exit 1 with no
>   output. Invoke binaries through `./node_modules/.bin/…` instead.
> - Never verify a command by piping it to `tail`: a pipeline's exit code is the
>   last element's, so `npm run build | tail` reports success even when the
>   build fails. Redirect to a file and check `$?`.

- [ ] **Step 2: Write the failing test**

Append to `frontend/tests/components/DeliveryMap.test.tsx`:

`afterEach`, `beforeEach`, and `vi` are already imported by Task 10 — do not
add a second import line.

```tsx
describe('DeliveryMap with a maps key', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', 'test-browser-key')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders the map container and keeps the ETA text', () => {
    render(<DeliveryMap tracking={base} />)
    expect(screen.getByTestId('delivery-map')).toBeInTheDocument()
    expect(screen.getByText(/12 min/)).toBeInTheDocument()
  })

  it('falls back to text when the driver position is unknown', () => {
    render(<DeliveryMap tracking={{ ...base, driver: null }} />)
    expect(screen.queryByTestId('delivery-map')).not.toBeInTheDocument()
    expect(screen.getByText(/locating your driver/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/components/DeliveryMap.test.tsx`
Expected: no element with `data-testid="delivery-map"`.

- [ ] **Step 4: Add the map branch**

In `frontend/src/components/DeliveryMap.tsx`, add the imports and the map subtree:

```tsx
import { AdvancedMarker, APIProvider, Map, useMap } from '@vis.gl/react-google-maps'
import { useEffect } from 'react'
```

Add a bounds-fitting child and the map component:

```tsx
function FitBounds({ points }: { points: Coordinate[] }) {
  const map = useMap()
  useEffect(() => {
    if (!map || points.length < 2) return
    // A bounds *literal* rather than new google.maps.LatLngBounds(): no global
    // SDK access, so this needs no @types/google.maps and does not throw in
    // jsdom where the SDK never loads.
    const lats = points.map((p) => p.latitude)
    const lngs = points.map((p) => p.longitude)
    map.fitBounds(
      {
        north: Math.max(...lats),
        south: Math.min(...lats),
        east: Math.max(...lngs),
        west: Math.min(...lngs),
      },
      64,
    )
  }, [map, points])
  return null
}

function TrackingMap({ tracking, apiKey }: { tracking: Tracking; apiKey: string }) {
  const driver = tracking.driver!
  const points = [tracking.driver, tracking.restaurant, tracking.destination]
    .filter((p): p is Coordinate => p !== null)

  return (
    <div className="track-map" data-testid="delivery-map">
      <APIProvider apiKey={apiKey}>
        <Map
          defaultCenter={{ lat: driver.latitude, lng: driver.longitude }}
          defaultZoom={13}
          disableDefaultUI
          gestureHandling="greedy"
          mapId="delivery-tracking"
        >
          <AdvancedMarker
            position={{ lat: driver.latitude, lng: driver.longitude }}
            title="Your driver"
          />
          {tracking.restaurant && (
            <AdvancedMarker
              position={{ lat: tracking.restaurant.latitude, lng: tracking.restaurant.longitude }}
              title="Restaurant"
            />
          )}
          {tracking.destination && (
            <AdvancedMarker
              position={{ lat: tracking.destination.latitude, lng: tracking.destination.longitude }}
              title="Your address"
            />
          )}
          <FitBounds points={points} />
        </Map>
      </APIProvider>
    </div>
  )
}
```

Import the `Coordinate` type alongside `Tracking`, and render the map inside `DeliveryMap` above the text body:

```tsx
  const apiKey = mapsKey()

  return (
    <div className="track-card">
      {apiKey && tracking.driver && (
        <TrackingMap tracking={tracking} apiKey={apiKey} />
      )}
      <span className="track-pulse" aria-hidden />
      …
```

The map renders **only** when both a key and a driver position exist. The text body stays in every case, so the ETA is always readable and the tests from Task 10 keep passing unchanged.

- [ ] **Step 5: Add the map styles**

Append to `frontend/src/layout.css`:

```css
.track-map {
  width: 100%;
  height: 260px;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}
```

The `track-card` rule may be a flex row; if the map lands beside the text rather than above it, change `.track-card` to `flex-wrap: wrap` or give the map `flex-basis: 100%`. Check the existing rule before editing it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/components/DeliveryMap.test.tsx`
Expected: 7 passed. `APIProvider` does not fetch anything in jsdom, so the container renders without a network call; if it throws, wrap the assertion target in the `data-testid` div outside `APIProvider` as written above — the div is deliberately the outer element for exactly this reason.

- [ ] **Step 7: Verify everything, both stacks**

Run, in order:

```bash
pytest -q
flake8 src
cd frontend && npm test
cd frontend && npm run build
```

Expected: backend suite green with coverage, flake8 silent, all Vitest suites pass, clean typecheck and bundle.

- [ ] **Step 8: Manual end-to-end check**

With Postgres and Redis running:

```bash
alembic upgrade head
docker compose up --build      # or run the API and Vite dev server directly
```

1. Register or sign in as a customer, add an address with a real street, city, and postal code, and confirm `GET /users/me/addresses` returns non-null `latitude` / `longitude` — this proves live geocoding works.
2. Place an order; as the restaurant owner accept it and advance it to `READY_FOR_PICKUP`.
3. Sign in as a driver in a second browser, turn on **Share my location**, and allow the permission prompt.
4. As the customer, open the order and confirm the map shows three markers, and that `eta_source` is `google` in the network response — not `estimate`.
5. Have the driver mark the order picked up, and confirm the restaurant marker drops out of the route and the ETA shortens.

- [ ] **Step 9: Hand the commit to the human**

```
feat(frontend): live Google map on the tracking panel

Renders driver, restaurant, and destination markers fitted to bounds when
a browser Maps key is configured, keeping the text ETA in every case so
an unkeyed build still tracks.
```

---

## Notes for the implementer

- **`redis` is `None` in many tests.** Every function that takes it must tolerate `None` — `estimate_for_order`, `invalidate`, and `tracking_for_order` all do. Do not add a `redis` requirement to a code path that a unit test reaches without one.
- **Why the driver's position is never cached.** Redis GEO reads are local and cheap; the Routes API is metered. Caching the position too would make the marker jump every 30 seconds instead of gliding every 5.
- **Why a failed re-geocode clears coordinates.** Keeping the old point for a new street address routes the driver to the previous address. Ungeocoded degrades visibly; wrong coordinates fail silently and badly.
- **Google is not mocked by patching.** `httpx.MockTransport` drives the adapter's real request-building code, so a malformed field mask or wrong header name fails a test instead of reaching production.
- **The frontend `.env` currently reuses the server key.** That is fine on localhost and wrong in production; `frontend/.env` says so, and a referrer-restricted browser key is a deployment step, not a code change.

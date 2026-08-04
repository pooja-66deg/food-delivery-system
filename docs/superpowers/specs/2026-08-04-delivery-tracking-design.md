# Design — Live driver tracking & ETA

Date: 2026-08-04
Branch: `feat/delivery-tracking`
Phase: H (see `2026-07-31-auth-forms-and-role-routing-design.md`)
Status: awaiting review

## Problem

The delivery module has the plumbing for live tracking and none of the parts
that make it live.

- **Nothing publishes a position.** `POST /delivery/location` exists and writes
  to a Redis GEO index; no client calls it. `DriverPage` renders assignment
  cards and accept/pickup/deliver buttons only.
- **Nothing populates the online set.** `_nearest_available_driver` picks the
  closest driver from `drivers:geo`, which is written solely by
  `update_location`. In practice that index is empty, so nearest-driver
  assignment silently degrades to `_find_available_driver` — "any free driver"
  — on every order.
- **The customer sees raw coordinates.** `OrderDetailPage` polls
  `GET /delivery/orders/{id}/tracking` every 5 seconds and prints
  `Driver near 12.9716, 77.5946`. Because no driver ever posts a location, the
  real rendering is the `Locating your driver…` branch, permanently.
- **There is no ETA and nothing to compute one from.** No routing or distance
  code exists. `Address` — the delivery destination — stores
  `line1 / line2 / city / postal_code` and no coordinates, so even the endpoint
  of the journey is unknown.

## Decisions

- **ETAs are computed server-side and returned in the tracking payload.** One
  source of truth, testable under `pytest` with a fake provider, one place that
  controls API quota, and a number the backend can reuse later for an
  "arriving soon" notification. Computing it in the browser via the Maps JS
  `DirectionsService` would make the ETA exist only where a browser key is
  configured, be unverifiable in tests, and be useless to the server.
- **Google is the primary provider; haversine is the fallback and the test
  double.** Both the Routes API and the Geocoding API are verified working
  against the configured key. `HaversineRouting` is not a placeholder — it is
  what runs when Google is unreachable, out of quota, or unconfigured, and it is
  what the tests assert against because it is deterministic.
- **Every geographic field is nullable and every consumer degrades.** An
  ungeocoded address, a driver who hasn't shared a position, and a restaurant
  without coordinates each yield `null` rather than an error or a fabricated
  number. `eta_minutes: null` is a real state the UI renders honestly.
- **Location sharing is opt-in, never implicit.** The driver flips a switch. A
  page that started tracking a person's position because they happened to have
  an active delivery would be tracking without consent, and could not put a
  driver online to receive their first offer.
- **Polling stays.** Extending the existing 5-second `setInterval` costs
  nothing and works behind any proxy. A WebSocket adds connection lifecycle,
  auth-over-socket, reconnect logic, and a new test harness to deliver the same
  5-second granularity.
- **Two API keys, never one.** A browser key is public and referrer-restricted;
  a server key carries Routes and Geocoding permission and must never reach the
  client.

## Configuration

Already landed, since `Settings` uses `extra='forbid'` and the app will not
start with `.env` keys it does not declare.

`src/config.py`:

```python
google_maps_api_key: Optional[str] = None   # server: Routes + Geocoding
delivery_average_speed_kmh: float = 25.0    # fallback ETA road speed
delivery_eta_cache_seconds: int = 30        # per-order ETA cache TTL
```

Mirrored in `.env` and `.env.example`. The browser key is
`VITE_GOOGLE_MAPS_API_KEY` in `frontend/.env` (gitignored via the anchored
`.env` rule) and `frontend/.env.example`.

For local development the same key value serves both; before deploying, a
second key restricted by HTTP referrer with only the Maps JavaScript API
enabled must be used for the browser. This is noted in `frontend/.env`.

## Backend

### `src/modules/delivery/providers.py` (new)

Protocol + implementations, following `payments/providers.py`.

```python
@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float

@dataclass(frozen=True)
class RouteEstimate:
    distance_km: float
    duration_minutes: int
    source: str          # "google" | "estimate"

class RoutingProvider(Protocol):
    async def route(self, waypoints: list[Coordinate]) -> RouteEstimate | None: ...

class GeocodeProvider(Protocol):
    async def geocode(self, line1: str, city: str, postal_code: str) -> Coordinate | None: ...
```

`route` takes a **waypoint list**, not an origin/destination pair, because the
pre-pickup leg is driver → restaurant → destination. Fewer than two waypoints,
or any `None` among them, returns `None`.

- **`HaversineRouting`** — great-circle distance between consecutive waypoints,
  multiplied by a `1.3` road-winding factor, divided by
  `delivery_average_speed_kmh`, rounded up, floored at 1 minute.
  `source="estimate"`. Pure computation, no I/O.
- **`GoogleRoutesProvider`** — `POST routes.googleapis.com/directions/v2:computeRoutes`
  with `travelMode: DRIVE`, intermediate waypoints for the middle legs, and a
  `X-Goog-FieldMask` of `routes.duration,routes.distanceMeters` so the response
  stays small. `source="google"`. Wraps `HaversineRouting` and delegates to it
  on any failure.
- **`NullGeocoder`** — returns `None`, logs at debug level.
- **`GoogleGeocoder`** — Geocoding API; `None` on `ZERO_RESULTS`, any non-`OK`
  status, or a transport error.

`geocode` deliberately omits `line2`. Apartment and unit numbers do not improve
a geocode and frequently defeat it.

Selection follows the exact shape `payments` uses: a `routing_provider()` /
`geocode_provider()` factory in `providers.py` keyed on
`settings.google_maps_api_key` being set, and callers taking an optional
`provider: RoutingProvider | None = None` argument that defaults to the factory
— the `provider = provider or provider_for(...)` idiom in
`payments/service.py`. That argument is how tests inject a fake without
patching.

### Failure handling

Two classes of failure, deliberately treated differently:

- **Configuration failures** — HTTP `403`, or a `REQUEST_DENIED` /
  `PERMISSION_DENIED` status. These do not heal on retry: a disabled API, a
  revoked key, or lapsed billing produces the same response on every call.
  `GoogleRoutesProvider` logs a warning once, sets `delivery:maps_disabled` in
  Redis with a 10-minute TTL, and suppresses further Google calls while that
  flag is present. Without this, a misconfigured key costs a doomed round trip
  on every ETA computation.
- **Transient failures** — timeout, `5xx`, malformed body. Fall back to
  haversine for that one call and retry normally on the next.

Neither class ever propagates. A tracking request must not return `500`
because Google is unavailable.

### `src/modules/delivery/eta.py` (new)

Assembles the estimate for an order, keeping the provider ignorant of domain
concepts and the service ignorant of routing mechanics.

- `waypoints_for(delivery, driver_loc, restaurant, destination) -> list[Coordinate]`
  — before `PICKED_UP`: `[driver, restaurant, destination]`; from `PICKED_UP`
  onward: `[driver, destination]`. Drops `None` entries; returns `[]` when
  fewer than two survive.
- `estimate_for_order(redis, delivery, ...) -> RouteEstimate | None` — reads
  `delivery:eta:{order_id}` from Redis, computes and caches on a miss with TTL
  `delivery_eta_cache_seconds`.
- `invalidate(redis, order_id)` — deletes the cache key. Called by
  `accept_assignment`, `reject_assignment`, `pickup`, and `deliver`, so the leg
  switch at pickup and a driver change on reject both take effect on the next
  poll instead of up to 30 seconds later. `reject_assignment` already receives
  `redis`; the other three take it as a new optional argument, matching how
  `redis` is already threaded through `assign_for_order`.

The driver's position is **not** cached — it is read fresh from Redis GEO on
every request. The marker therefore moves at 5-second granularity while the ETA
number refreshes at 30, which is the right trade: position is cheap and local,
routing is a metered network call.

### `tracking_for_order`

Keeps its authorisation exactly as-is — `get_order_for_user` first, so the
customer / restaurant / admin visibility rules and the 403/404 behaviour are
unchanged. It gains the restaurant and destination lookups and the ETA call,
and returns a typed `TrackingRead` in place of today's bare `dict`:

```python
class TrackingRead(BaseModel):
    order_id: int
    status: str
    driver_id: int | None
    driver: CoordinateRead | None        # live, from Redis GEO
    restaurant: CoordinateRead | None
    destination: CoordinateRead | None
    eta_minutes: int | None
    distance_km: float | None
    eta_source: str | None               # "google" | "estimate" | None
```

`eta_source` exists so customer-facing copy can honestly mark the haversine
path as an estimate, and so tests can assert which provider ran.

The `location` key is renamed to `driver`. Three call sites move with it:
`frontend/src/api/delivery.ts` (the `Tracking` interface), `OrderDetailPage`,
and `tests/modules/delivery/test_location.py:79`, which asserts
`body["location"] is not None`. Nothing else reads the key.

`Delivery.driver_id` is already exposed and unchanged; the driver's *name* and
phone are not added here — that is a privacy decision worth making
deliberately, not a side effect of a tracking change.

### Geocoding addresses

Migration: `latitude` and `longitude`, both nullable `Float`, on `addresses` —
the same nullable pair `restaurants` already carries. Nullable is load-bearing:
every existing row stays valid and `None` is the signal to degrade.

`users/profile.py`:

- `add_address` geocodes after validation and stores the result when non-`None`.
- `update_address` re-geocodes **only** when `line1`, `city`, or `postal_code`
  changes, so editing a label or promoting a default costs no API call.
- Geocoding never fails a write. A provider error or a no-match saves the
  address without coordinates.

`AddressResponse` exposes both fields so the frontend can distinguish a
mappable address from an unmappable one.

`tests/conftest.py` must add `google_maps_api_key` to the
`_no_third_party_credentials` autouse fixture. Without it the suite would make
live Google calls on any developer machine with the key in `.env` — exactly the
failure that fixture already prevents for Stripe.

## Frontend

### `useDriverLocation` hook

Owns geolocation and the two POSTs; `DriverPage` stays presentational.

- On enable: `POST /delivery/status {online: true}`, then
  `navigator.geolocation.watchPosition` with `enableHighAccuracy`.
- On disable: `POST /delivery/status {online: false}`, which already removes the
  GEO entry in `location.set_online`, and `clearWatch`.
- Throttle: `POST /delivery/location` at most once per 10 seconds, and only when
  the position moved at least 25 metres. `watchPosition` fires far more often
  than either bound.
- Off by default. State persisted in `localStorage` so a mid-shift refresh does
  not silently stop sharing.
- Exposes a discriminated status: `off`, `sharing` (with `lastUpdate`),
  `denied`, `unavailable`, `unsupported`. A driver whose location is not
  reaching the server must be told, not left guessing.

### `DriverPage`

A share-location toggle plus a status line driven by the hook, and a next-stop
link per active delivery: `https://www.google.com/maps/dir/?api=1&destination=lat,lng`
— a plain URL needing no key or SDK, which opens the native app on a phone.
Before pickup the next stop is the restaurant; from `PICKED_UP` it is the
customer. The link is omitted, not dead, when the coordinate is unknown.

**The driver cannot use the tracking endpoint.** `tracking_for_order` goes
through `get_order_for_user`, which admits the customer, the owning restaurant,
and admins — a driver raises `ForbiddenException`. So `DeliveryRead` gains
`restaurant` and `destination` coordinates and the driver reads them from
`GET /delivery/assignments`, which they already poll. Widening the tracking
endpoint's access would create a second path to a customer's address for a
narrower need; attaching two coordinates to a list the driver is already
entitled to does not.

The existing assignment cards and action buttons are otherwise untouched.

### `DeliveryMap` component

Replaces the coordinate text at `OrderDetailPage`, inside the existing
`OUT_FOR_DELIVERY` condition.

- **With a browser key**: `@googlemaps/js-api-loader` — Google's own loader,
  which brings `@types/google.maps` with it. Three markers (driver, restaurant,
  destination), map fitted to their bounds. The map is created once per mount and
  then *mutated* as polls arrive, so the marker moves without the viewport
  re-fitting under the user or the canvas flickering.

  > **Revised during implementation.** The design originally specified
  > `@vis.gl/react-google-maps`, the React wrapper. It cannot be installed in
  > this environment: npm fails while extracting its tarball and prints no
  > diagnostic, reproducibly, across three attempts with a cleared cache and in
  > the correct directory. `@googlemaps/js-api-loader` installs cleanly, so the
  > ~40 lines of React lifecycle the wrapper would have provided are written by
  > hand in `useTrackingMap`. Same visible result, one fewer dependency.
- **Without a key, or if the Maps script fails to load**: a text panel —
  `Arriving in ~12 min · 3.4 km away (estimated)` — plus the driver's
  coordinates. Same component, one branch, same tests.
- **No driver position yet**: `Locating your driver…`, as today.
- `(estimated)` is appended only when `eta_source === 'estimate'`.

## Test plan

Written test-first, per the repository TDD convention.

### Backend — `tests/modules/delivery/`

| Test | Asserts |
| --- | --- |
| `test_routing.py` | Haversine distance between known coordinates; multi-leg waypoint sum; 1-minute floor; `source == "estimate"`; `None` for fewer than two waypoints |
| `test_routing.py` | `GoogleRoutesProvider` parses `duration`/`distanceMeters`; falls back to haversine on timeout and on `5xx`; on `403` sets `delivery:maps_disabled` and skips the HTTP call while the flag is present |
| `test_eta.py` | Leg selection: `[driver, restaurant, destination]` before pickup, `[driver, destination]` from `PICKED_UP`; `None` when the destination is ungeocoded or the driver has no position |
| `test_eta.py` | Redis cache hit returns without invoking the provider; the key is deleted on a delivery status change |
| `test_api.py` | `TrackingRead` shape, including `eta_minutes` / `eta_source`; unchanged 403 for a foreign order and 404 for a missing delivery |

Google providers are tested against a stubbed HTTP transport — no live calls in
the suite.

### Backend — `tests/modules/users/`

| Test | Asserts |
| --- | --- |
| `test_addresses.py` | Creating an address stores geocoded coordinates; a provider returning `None` still saves the address with `null` coordinates |
| `test_addresses.py` | Editing `line1` re-geocodes; editing only `label` or `is_default` does not |

### Frontend — `frontend/tests/`

| Test | Asserts |
| --- | --- |
| `lib/useDriverLocation.test.ts` | Enabling posts status then location; second update inside 10s or under 25m is suppressed; denied permission surfaces `denied` and posts nothing; disabling posts `online: false` and clears the watch |
| `components/DeliveryMap.test.tsx` | Renders the text fallback with no key configured and the map container with one; `(estimated)` appears only for `eta_source === 'estimate'`; `Locating your driver…` when `driver` is `null` |

## Verification

```bash
pytest                          # full suite with coverage
flake8 src                      # must stay clean
cd frontend && npm test         # vitest
cd frontend && npm run build    # tsc typecheck + vite build
alembic upgrade head            # addresses lat/lon migration applies
```

Manual check: sign in as a driver, enable location sharing, confirm the status
line shows a recent update; as the customer on that order, confirm the map
renders three markers and an ETA that changes as the driver moves.

## Out of scope

- Restaurant-facing courier ETA and the admin live-driver map — phase I
  (`feat/admin-and-analytics`).
- Route polylines and turn-by-turn navigation. The deep link hands navigation
  to Google Maps, which does it better.
- WebSocket or SSE transport. Revisit only if 5-second granularity proves
  insufficient.
- "Arriving soon" push notifications. `estimate_for_order` is the hook they
  would use.
- Driver vehicle, licence, and delivery-stats fields.
- Backfilling coordinates for addresses created before this branch. A one-off
  script, not application code.

## Risks

- **Quota and cost.** A 5-second poll on a long delivery is ~720 tracking
  requests per hour per viewer. The 30-second ETA cache reduces Routes calls to
  ~120/hour/order, and the cache is per order rather than per viewer, so
  multiple watchers of the same order share it. Worth watching before
  production, where the cache TTL is the single lever.
- **Mobile geolocation is unreliable.** Backgrounded tabs are throttled or
  suspended, so a driver's position can go stale without any error. The status
  line shows the last update time so staleness is visible rather than silent;
  a native driver app is the real fix.
- **The migration adds columns to `addresses`, which `orders.address_id`
  references.** Additive and nullable, so no existing row or query breaks.
- **A browser key is public by construction.** Referrer restriction is the only
  control, and it is a deployment step outside this branch. Documented in
  `frontend/.env` rather than assumed.

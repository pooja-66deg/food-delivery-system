"""Delivery-zone serviceability: can this restaurant deliver to this address?

A restaurant serves an address when the address falls inside the restaurant's
delivery radius. That needs three things — coordinates on the restaurant,
coordinates on the address, and a radius — and any of them can be missing: a
restaurant created before geocoding existed has no coordinates, and an address
that Google could not resolve saved anyway (by design, see
``providers.GoogleGeocoder``). When either end is unmappable the check degrades
to the city match that used to be the only rule.

Two consequences of preferring the radius, both intended:

- Same city, far apart is now **rejected**. A restaurant in one corner of a
  large city no longer "delivers" 40 km across it.
- Different cities, close together is now **accepted**. Neighbouring towns a few
  kilometres apart are a real delivery area that a string comparison refused.
"""
from dataclasses import dataclass

from app.config import settings
# A pure geometry helper, not a reach into the delivery domain's tables — the
# haversine primitive happens to live with the routing providers that need it.
from app.providers import Coordinate, haversine_km

# Which rule decided a verdict, so callers can word a rejection accurately
# rather than guessing which check ran.
BASIS_RADIUS = "radius"
BASIS_CITY = "city"


@dataclass(frozen=True)
class ZoneVerdict:
    serviceable: bool
    basis: str
    # Straight-line distance and the limit it was compared against. Both None
    # when the verdict came from a city match, where no distance was computed.
    distance_km: float | None = None
    radius_km: float | None = None


def effective_radius_km(restaurant) -> float:
    """The radius to enforce for a restaurant.

    Its own setting when it has one, otherwise the platform default. Falling
    back to a default rather than to "unlimited" is deliberate: a geocoded
    restaurant that never set a radius should get a sane zone, not the whole
    map.
    """
    configured = restaurant.delivery_radius_km
    if configured is None or float(configured) <= 0:
        return float(settings.delivery_default_radius_km)
    return float(configured)


def _coord(obj) -> Coordinate | None:
    """A Coordinate from anything carrying latitude/longitude, or None."""
    if obj is None or obj.latitude is None or obj.longitude is None:
        return None
    return Coordinate(latitude=obj.latitude, longitude=obj.longitude)


def same_city(restaurant, address) -> bool:
    """Case- and whitespace-insensitive city equality.

    The pre-radius rule, kept as the fallback so "Surat" / "surat" / " surat "
    all still count as the same city.
    """
    return (address.city or "").strip().casefold() == (restaurant.city or "").strip().casefold()


def check(restaurant, address) -> ZoneVerdict:
    """Whether ``restaurant`` delivers to ``address``, and on what grounds."""
    origin, destination = _coord(restaurant), _coord(address)

    if origin is None or destination is None:
        return ZoneVerdict(serviceable=same_city(restaurant, address), basis=BASIS_CITY)

    radius = effective_radius_km(restaurant)
    distance = round(haversine_km(origin, destination), 2)
    return ZoneVerdict(
        serviceable=distance <= radius,
        basis=BASIS_RADIUS,
        distance_km=distance,
        radius_km=radius,
    )


def rejection_message(restaurant, verdict: ZoneVerdict) -> str:
    """Customer-facing reason an address is out of zone.

    The radius wording names the actual numbers, because "too far" without a
    distance leaves the customer unable to tell whether a different saved
    address would work.
    """
    if verdict.basis == BASIS_RADIUS:
        return (
            f"That address is {verdict.distance_km} km away — "
            f"{restaurant.name} delivers within {verdict.radius_km} km."
        )
    return f"We only deliver within {restaurant.city} for this restaurant."

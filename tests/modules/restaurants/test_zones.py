"""Delivery-zone serviceability: radius when geocoded, city match otherwise."""
from dataclasses import dataclass

import pytest

from src.config import settings
from src.modules.restaurants import zones


@dataclass
class FakePlace:
    """Stands in for a Restaurant or an Address — the zone check only reads
    city/latitude/longitude/name and the radius, so a real row buys nothing."""

    city: str = "Metropolis"
    latitude: float | None = None
    longitude: float | None = None
    delivery_radius_km: float | None = None
    name: str = "Pizza"


# Two points roughly 4.5 km apart, and one roughly 44 km away.
NEAR = (21.2000, 72.8400)
ORIGIN = (21.1702, 72.8311)
FAR = (21.5650, 72.8311)


def _restaurant(**kw) -> FakePlace:
    return FakePlace(latitude=ORIGIN[0], longitude=ORIGIN[1], **kw)


def _address(point, city="Metropolis") -> FakePlace:
    return FakePlace(city=city, latitude=point[0], longitude=point[1])


def test_address_inside_the_radius_is_serviceable():
    verdict = zones.check(_restaurant(delivery_radius_km=10), _address(NEAR))

    assert verdict.serviceable
    assert verdict.basis == zones.BASIS_RADIUS
    assert verdict.radius_km == 10
    assert 3 < verdict.distance_km < 6


def test_same_city_but_beyond_the_radius_is_rejected():
    """The gap the city match could not see: 44 km inside one city."""
    verdict = zones.check(_restaurant(delivery_radius_km=10), _address(FAR))

    assert not verdict.serviceable
    assert verdict.basis == zones.BASIS_RADIUS
    assert verdict.distance_km > 40


def test_different_city_within_the_radius_is_accepted():
    """The other half: a neighbouring town a few km away is a real zone."""
    verdict = zones.check(_restaurant(delivery_radius_km=10), _address(NEAR, city="Gotham"))

    assert verdict.serviceable
    assert verdict.basis == zones.BASIS_RADIUS


@pytest.mark.parametrize(
    "restaurant, address",
    [
        (FakePlace(), _address(NEAR)),                      # restaurant ungeocoded
        (_restaurant(), FakePlace(city="Metropolis")),       # address ungeocoded
        (FakePlace(), FakePlace()),                          # neither geocoded
    ],
)
def test_falls_back_to_city_when_either_end_is_unmappable(restaurant, address):
    verdict = zones.check(restaurant, address)

    assert verdict.basis == zones.BASIS_CITY
    assert verdict.serviceable
    # Nothing was measured, so nothing is reported.
    assert verdict.distance_km is None
    assert verdict.radius_km is None


def test_city_fallback_rejects_a_different_city():
    verdict = zones.check(FakePlace(city="Metropolis"), FakePlace(city="Gotham"))

    assert not verdict.serviceable
    assert verdict.basis == zones.BASIS_CITY


@pytest.mark.parametrize("city", ["metropolis", " Metropolis ", "METROPOLIS"])
def test_city_fallback_ignores_case_and_padding(city):
    assert zones.check(FakePlace(city="Metropolis"), FakePlace(city=city)).serviceable


def test_unset_radius_uses_the_platform_default_not_unlimited():
    """A geocoded restaurant that never chose a radius still gets a zone."""
    restaurant = _restaurant(delivery_radius_km=None)

    assert zones.effective_radius_km(restaurant) == settings.delivery_default_radius_km
    assert not zones.check(restaurant, _address(FAR)).serviceable


@pytest.mark.parametrize("bad", [0, -5])
def test_nonsense_radius_falls_back_to_the_default(bad):
    """A zero or negative radius would service nothing; treat it as unset."""
    assert zones.effective_radius_km(_restaurant(delivery_radius_km=bad)) == (
        settings.delivery_default_radius_km
    )


def test_radius_rejection_message_names_the_distance_and_limit():
    restaurant = _restaurant(delivery_radius_km=10, name="Pizza Palace")
    verdict = zones.check(restaurant, _address(FAR))

    message = zones.rejection_message(restaurant, verdict)

    assert str(verdict.distance_km) in message
    assert "10" in message
    assert "Pizza Palace" in message


def test_city_rejection_message_names_the_city():
    restaurant = FakePlace(city="Metropolis")
    verdict = zones.check(restaurant, FakePlace(city="Gotham"))

    assert "Metropolis" in zones.rejection_message(restaurant, verdict)

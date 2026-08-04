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

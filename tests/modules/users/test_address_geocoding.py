"""Address coordinates: storage, exposure, and geocode-on-save."""
import pytest

from src.modules.delivery.providers import Coordinate
from src.modules.users import profile
from src.modules.users.models import User
from src.modules.users.schemas import AddressCreate, AddressUpdate


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


@pytest.mark.asyncio
async def test_failed_regeocode_clears_stale_coordinates(db_session):
    """Stale coordinates for a new street address would route to the old one."""
    user = await _user(db_session)
    geocoder = FakeGeocoder()
    address = await profile.add_address(
        db_session, user,
        AddressCreate(line1="1 Main St", city="Bengaluru", postal_code="560001"),
        geocoder=geocoder,
    )
    assert address.latitude is not None

    geocoder.result = None
    await profile.update_address(
        db_session, user, address.id, AddressUpdate(line1="unfindable"),
        geocoder=geocoder,
    )

    assert address.latitude is None
    assert address.longitude is None

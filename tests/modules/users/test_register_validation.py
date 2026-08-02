"""Registration input rules: names are letters-only, phone normalizes to E.164."""
import pytest

BASE = {"email": "v@x.com", "phone": "9876543210", "first_name": "Alex",
        "last_name": "Rivera", "password": "supersecret1", "role": "customer"}


async def _register(api_client, **overrides):
    return await api_client.post("/auth/register", json={**BASE, **overrides})


@pytest.mark.asyncio
async def test_valid_registration_succeeds(api_client):
    assert (await _register(api_client)).status_code == 201


@pytest.mark.asyncio
async def test_plus_prefixed_phone_allowed(api_client):
    assert (await _register(api_client, email="a@x.com", phone="+15550002222")).status_code == 201


@pytest.mark.parametrize("field,value", [
    ("first_name", "Alex1"),
    ("first_name", "Al@x"),
    ("last_name", "Rivera_"),
    ("last_name", "R2D2"),
])
@pytest.mark.asyncio
async def test_names_reject_numbers_and_specials(api_client, field, value):
    resp = await _register(api_client, **{field: value})
    assert resp.status_code == 422


@pytest.mark.parametrize("phone", ["55512ab345", "call-me", "555 123 4567!", "12345"])
@pytest.mark.asyncio
async def test_phone_rejects_unusable_numbers(api_client, phone):
    assert (await _register(api_client, phone=phone)).status_code == 422


@pytest.mark.parametrize("typed", ["9876543210", "098765 43210", "+91-98765-43210"])
@pytest.mark.asyncio
async def test_phone_is_stored_in_e164(api_client, typed):
    resp = await _register(api_client, phone=typed)
    assert resp.status_code == 201
    assert resp.json()["phone"] == "+919876543210"


@pytest.mark.asyncio
async def test_same_number_typed_differently_is_one_account(api_client):
    """Normalizing at the schema boundary is what makes the uniqueness check bite."""
    assert (await _register(api_client, phone="9876543210")).status_code == 201
    clash = await _register(api_client, email="other@x.com", phone="+91 98765 43210")
    assert clash.status_code == 409

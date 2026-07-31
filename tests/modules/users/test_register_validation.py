"""Registration input rules: names are letters-only, phone is numeric."""
import pytest

BASE = {"email": "v@x.com", "phone": "15550001111", "first_name": "Alex",
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


@pytest.mark.parametrize("phone", ["55512ab345", "call-me", "555 123 4567!"])
@pytest.mark.asyncio
async def test_phone_rejects_non_numeric(api_client, phone):
    assert (await _register(api_client, phone=phone)).status_code == 422

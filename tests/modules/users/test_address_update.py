"""Tests for editing an existing delivery address."""

import pytest

from src.core.exceptions import NotFoundException
from src.modules.users import profile, service
from src.modules.users.schemas import AddressCreate, AddressUpdate, UserRegister


def _registration(**overrides) -> UserRegister:
    base = dict(
        email="addr@example.com",
        phone="+15553340000",
        first_name="Addy",
        last_name="Ress",
        password="supersecret1",
    )
    base.update(overrides)
    return UserRegister(**base)


def _address(**overrides) -> AddressCreate:
    base = dict(label="home", line1="1 Main St", city="Metropolis", postal_code="12345")
    base.update(overrides)
    return AddressCreate(**base)


@pytest.mark.asyncio
async def test_update_changes_only_the_named_fields(db_session):
    user = await service.register_user(db_session, _registration())
    created = await profile.add_address(db_session, user, _address())

    updated = await profile.update_address(
        db_session, user, created.id, AddressUpdate(line1="99 Side Rd")
    )

    assert updated.line1 == "99 Side Rd"
    assert updated.city == "Metropolis"      # untouched
    assert updated.postal_code == "12345"    # untouched
    assert updated.label == "home"           # untouched


@pytest.mark.asyncio
async def test_update_can_clear_line2(db_session):
    user = await service.register_user(db_session, _registration())
    created = await profile.add_address(db_session, user, _address(line2="Apt 4"))

    updated = await profile.update_address(
        db_session, user, created.id, AddressUpdate(line2=None)
    )

    assert updated.line2 is None


@pytest.mark.asyncio
async def test_promoting_to_default_demotes_the_previous_default(db_session):
    user = await service.register_user(db_session, _registration())
    first = await profile.add_address(db_session, user, _address(label="home", is_default=True))
    second = await profile.add_address(db_session, user, _address(label="work"))

    await profile.update_address(db_session, user, second.id, AddressUpdate(is_default=True))

    addresses = {a.id: a for a in await profile.list_addresses(db_session, user)}
    assert addresses[first.id].is_default is False
    assert addresses[second.id].is_default is True


@pytest.mark.asyncio
async def test_update_not_owned_rejected(db_session):
    owner = await service.register_user(
        db_session, _registration(email="o2@example.com", phone="+15553340010"))
    other = await service.register_user(
        db_session, _registration(email="x2@example.com", phone="+15553340011"))
    created = await profile.add_address(db_session, owner, _address())

    with pytest.raises(NotFoundException):
        await profile.update_address(db_session, other, created.id, AddressUpdate(city="Gotham"))


@pytest.mark.asyncio
async def test_update_missing_address_rejected(db_session):
    user = await service.register_user(db_session, _registration())

    with pytest.raises(NotFoundException):
        await profile.update_address(db_session, user, 9999, AddressUpdate(city="Gotham"))


@pytest.mark.asyncio
async def test_patch_route_updates_the_address(api_client):
    await api_client.post("/auth/register", json={
        "email": "patch@example.com", "phone": "+15553340020", "first_name": "Pat",
        "last_name": "Chey", "password": "supersecret1", "role": "customer"})
    tokens = (await api_client.post(
        "/auth/login", json={"email": "patch@example.com", "password": "supersecret1"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    created = (await api_client.post("/users/me/addresses", headers=headers, json={
        "label": "home", "line1": "1 Main St", "city": "Metropolis",
        "postal_code": "12345", "is_default": False})).json()

    resp = await api_client.patch(
        f"/users/me/addresses/{created['id']}", headers=headers, json={"label": "work"})

    assert resp.status_code == 200
    assert resp.json()["label"] == "work"
    assert resp.json()["line1"] == "1 Main St"


@pytest.mark.asyncio
async def test_patch_route_rejects_someone_elses_address(api_client):
    async def _account(email, phone):
        await api_client.post("/auth/register", json={
            "email": email, "phone": phone, "first_name": "Some", "last_name": "One",
            "password": "supersecret1", "role": "customer"})
        tokens = (await api_client.post(
            "/auth/login", json={"email": email, "password": "supersecret1"})).json()
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    owner = await _account("owner@example.com", "+15553340030")
    intruder = await _account("intruder@example.com", "+15553340031")

    created = (await api_client.post("/users/me/addresses", headers=owner, json={
        "label": "home", "line1": "1 Main St", "city": "Metropolis",
        "postal_code": "12345", "is_default": False})).json()

    resp = await api_client.patch(
        f"/users/me/addresses/{created['id']}", headers=intruder, json={"label": "stolen"})

    assert resp.status_code == 404

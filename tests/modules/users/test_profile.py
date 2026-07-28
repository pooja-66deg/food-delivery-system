"""Tests for profile updates and address management."""

import pytest

from src.core.exceptions import ConflictException, NotFoundException
from src.modules.users import profile, service
from src.modules.users.schemas import AddressCreate, UserRegister, UserUpdate


def _registration(**overrides) -> UserRegister:
    base = dict(
        email="prof@example.com",
        phone="+15553330000",
        first_name="Pro",
        last_name="File",
        password="supersecret1",
    )
    base.update(overrides)
    return UserRegister(**base)


def _address(**overrides) -> AddressCreate:
    base = dict(label="home", line1="1 Main St", city="Metropolis", postal_code="12345")
    base.update(overrides)
    return AddressCreate(**base)


@pytest.mark.asyncio
async def test_update_profile_changes_names(db_session):
    user = await service.register_user(db_session, _registration())

    updated = await profile.update_profile(
        db_session, user, UserUpdate(first_name="New", last_name="Name")
    )

    assert updated.first_name == "New"
    assert updated.last_name == "Name"


@pytest.mark.asyncio
async def test_update_profile_duplicate_phone_rejected(db_session):
    await service.register_user(db_session, _registration(email="a@example.com", phone="+15553330001"))
    user_b = await service.register_user(
        db_session, _registration(email="b@example.com", phone="+15553330002")
    )

    with pytest.raises(ConflictException):
        await profile.update_profile(db_session, user_b, UserUpdate(phone="+15553330001"))


@pytest.mark.asyncio
async def test_add_and_list_addresses(db_session):
    user = await service.register_user(db_session, _registration())

    created = await profile.add_address(db_session, user, _address())
    assert created.id is not None

    addresses = await profile.list_addresses(db_session, user)
    assert len(addresses) == 1
    assert addresses[0].line1 == "1 Main St"


@pytest.mark.asyncio
async def test_setting_default_address_unsets_previous(db_session):
    user = await service.register_user(db_session, _registration())

    first = await profile.add_address(db_session, user, _address(label="home", is_default=True))
    second = await profile.add_address(db_session, user, _address(label="work", is_default=True))

    addresses = {a.id: a for a in await profile.list_addresses(db_session, user)}
    assert addresses[first.id].is_default is False
    assert addresses[second.id].is_default is True


@pytest.mark.asyncio
async def test_delete_address(db_session):
    user = await service.register_user(db_session, _registration())
    created = await profile.add_address(db_session, user, _address())

    await profile.delete_address(db_session, user, created.id)

    assert await profile.list_addresses(db_session, user) == []


@pytest.mark.asyncio
async def test_delete_address_not_owned_rejected(db_session):
    owner = await service.register_user(db_session, _registration(email="o@example.com", phone="+15553330010"))
    other = await service.register_user(db_session, _registration(email="x@example.com", phone="+15553330011"))
    created = await profile.add_address(db_session, owner, _address())

    with pytest.raises(NotFoundException):
        await profile.delete_address(db_session, other, created.id)

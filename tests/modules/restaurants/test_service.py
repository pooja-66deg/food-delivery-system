"""Tests for the restaurants domain service layer."""

from decimal import Decimal

import pytest

from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.restaurants import service
from src.modules.restaurants.schemas import RestaurantCreate, RestaurantUpdate
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister


async def _owner(db_session, email="owner@example.com", phone="+15557770001"):
    return await users_service.register_user(
        db_session,
        UserRegister(
            email=email, phone=phone, first_name="Ola", last_name="Owner",
            password="supersecret1", role="restaurant",
        ),
    )


def _restaurant(**overrides) -> RestaurantCreate:
    base = dict(
        name="Pizza Palace",
        description="Wood-fired pizzas",
        city="Metropolis",
        address_line="1 Main St",
        phone="+15550000000",
        min_order_amount=Decimal("10.00"),
    )
    base.update(overrides)
    return RestaurantCreate(**base)


@pytest.mark.asyncio
async def test_create_restaurant_sets_owner(db_session):
    owner = await _owner(db_session)

    r = await service.create_restaurant(db_session, owner, _restaurant())

    assert r.id is not None
    assert r.owner_id == owner.id
    assert r.name == "Pizza Palace"
    assert r.is_open is False  # closed until the owner opens it


@pytest.mark.asyncio
async def test_get_restaurant_missing_raises(db_session):
    with pytest.raises(NotFoundException):
        await service.get_restaurant(db_session, 999)


@pytest.mark.asyncio
async def test_list_restaurants_filters_by_city_and_search(db_session):
    owner = await _owner(db_session)
    await service.create_restaurant(db_session, owner, _restaurant(name="Pizza Palace", city="Metropolis"))
    await service.create_restaurant(db_session, owner, _restaurant(name="Sushi Spot", city="Gotham"))
    await service.create_restaurant(db_session, owner, _restaurant(name="Pizza Hub", city="Metropolis"))

    assert len(await service.list_restaurants(db_session)) == 3
    assert len(await service.list_restaurants(db_session, city="Metropolis")) == 2
    pizzas = await service.list_restaurants(db_session, search="pizza")
    assert {r.name for r in pizzas} == {"Pizza Palace", "Pizza Hub"}


@pytest.mark.asyncio
async def test_update_restaurant_by_owner(db_session):
    owner = await _owner(db_session)
    r = await service.create_restaurant(db_session, owner, _restaurant())

    updated = await service.update_restaurant(
        db_session, r.id, owner, RestaurantUpdate(name="Pizza Palace II", is_open=True)
    )

    assert updated.name == "Pizza Palace II"
    assert updated.is_open is True


@pytest.mark.asyncio
async def test_update_restaurant_by_non_owner_forbidden(db_session):
    owner = await _owner(db_session)
    intruder = await _owner(db_session, email="intruder@example.com", phone="+15557770002")
    r = await service.create_restaurant(db_session, owner, _restaurant())

    with pytest.raises(ForbiddenException):
        await service.update_restaurant(db_session, r.id, intruder, RestaurantUpdate(name="Hacked"))

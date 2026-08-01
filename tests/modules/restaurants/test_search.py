"""Discovery: city filtering, cuisine-aware search, suggestions, popular cuisines."""

from decimal import Decimal

import pytest

from src.modules.restaurants import service
from src.modules.restaurants.schemas import RestaurantCreate
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
        cuisine="Italian",
        city="Metropolis",
        address_line="1 Main St",
        phone="+15550000000",
        min_order_amount=Decimal("10.00"),
    )
    base.update(overrides)
    return RestaurantCreate(**base)


async def _seed(db_session):
    """Three restaurants spanning two cities and three cuisines."""
    owner = await _owner(db_session)
    await service.create_restaurant(
        db_session, owner, _restaurant(name="Pizza Palace", city="Metropolis", cuisine="Italian")
    )
    await service.create_restaurant(
        db_session, owner, _restaurant(name="Sushi Spot", city="Gotham", cuisine="Japanese")
    )
    await service.create_restaurant(
        db_session, owner, _restaurant(name="Curry Corner", city="Metropolis", cuisine=None)
    )
    return owner


# ---------- city filter ----------

@pytest.mark.asyncio
async def test_city_filter_ignores_case(db_session):
    await _seed(db_session)

    found = await service.list_restaurants(db_session, city="metropolis")

    assert {r.name for r in found} == {"Pizza Palace", "Curry Corner"}


@pytest.mark.asyncio
async def test_city_filter_matches_partial_name(db_session):
    await _seed(db_session)

    found = await service.list_restaurants(db_session, city="metro")

    assert {r.name for r in found} == {"Pizza Palace", "Curry Corner"}


@pytest.mark.asyncio
async def test_city_filter_ignores_surrounding_whitespace(db_session):
    await _seed(db_session)

    found = await service.list_restaurants(db_session, city="  Gotham  ")

    assert {r.name for r in found} == {"Sushi Spot"}


# ---------- search term ----------

@pytest.mark.asyncio
async def test_search_matches_cuisine(db_session):
    await _seed(db_session)

    found = await service.list_restaurants(db_session, search="japanese")

    assert {r.name for r in found} == {"Sushi Spot"}


@pytest.mark.asyncio
async def test_search_still_matches_name(db_session):
    await _seed(db_session)

    found = await service.list_restaurants(db_session, search="pizza")

    assert {r.name for r in found} == {"Pizza Palace"}


@pytest.mark.asyncio
async def test_search_excludes_untagged_restaurants_on_cuisine_term(db_session):
    """A NULL cuisine must not match a cuisine-only term."""
    await _seed(db_session)

    found = await service.list_restaurants(db_session, search="italian")

    assert {r.name for r in found} == {"Pizza Palace"}


# ---------- suggestions ----------

@pytest.mark.asyncio
async def test_suggest_returns_nothing_below_two_characters(db_session):
    await _seed(db_session)

    assert await service.suggest_restaurants(db_session, "p") == []


@pytest.mark.asyncio
async def test_suggest_matches_name(db_session):
    await _seed(db_session)

    found = await service.suggest_restaurants(db_session, "piz")

    assert [r.name for r in found] == ["Pizza Palace"]


@pytest.mark.asyncio
async def test_suggest_matches_cuisine(db_session):
    await _seed(db_session)

    found = await service.suggest_restaurants(db_session, "japan")

    assert [r.name for r in found] == ["Sushi Spot"]


@pytest.mark.asyncio
async def test_suggest_respects_limit(db_session):
    owner = await _owner(db_session)
    for i in range(5):
        await service.create_restaurant(
            db_session, owner, _restaurant(name=f"Pizza {i}", cuisine="Italian")
        )

    found = await service.suggest_restaurants(db_session, "pizza", limit=3)

    assert len(found) == 3


# ---------- popular cuisines ----------

@pytest.mark.asyncio
async def test_popular_cuisines_orders_by_count(db_session):
    owner = await _owner(db_session)
    for i in range(3):
        await service.create_restaurant(
            db_session, owner, _restaurant(name=f"Italian {i}", cuisine="Italian")
        )
    await service.create_restaurant(db_session, owner, _restaurant(name="Sushi", cuisine="Japanese"))

    popular = await service.popular_cuisines(db_session)

    assert popular == [("Italian", 3), ("Japanese", 1)]


@pytest.mark.asyncio
async def test_popular_cuisines_excludes_null_and_blank(db_session):
    owner = await _owner(db_session)
    await service.create_restaurant(db_session, owner, _restaurant(name="Tagged", cuisine="Thai"))
    await service.create_restaurant(db_session, owner, _restaurant(name="Untagged", cuisine=None))
    await service.create_restaurant(db_session, owner, _restaurant(name="Blank", cuisine=""))

    popular = await service.popular_cuisines(db_session)

    assert popular == [("Thai", 1)]


@pytest.mark.asyncio
async def test_popular_cuisines_breaks_count_ties_by_name(db_session):
    """Deterministic ordering, otherwise the assertion above would be flaky."""
    owner = await _owner(db_session)
    await service.create_restaurant(db_session, owner, _restaurant(name="Z", cuisine="Zambian"))
    await service.create_restaurant(db_session, owner, _restaurant(name="A", cuisine="Afghan"))

    popular = await service.popular_cuisines(db_session)

    assert popular == [("Afghan", 1), ("Zambian", 1)]

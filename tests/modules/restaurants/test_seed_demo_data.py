"""The demo seeder must be safe to run repeatedly."""

import pytest
from sqlalchemy import func, select

from scripts.seed_demo_data import DEMO_OWNER_EMAIL, DEMO_RESTAURANTS, seed
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import User


async def _count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_seed_creates_the_demo_restaurants(db_session):
    await seed(db_session)

    assert await _count(db_session, Restaurant) == len(DEMO_RESTAURANTS)


@pytest.mark.asyncio
async def test_seed_creates_one_owner(db_session):
    await seed(db_session)

    owner = await db_session.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    assert owner is not None
    assert owner.role == "restaurant"


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session):
    await seed(db_session)
    first = await _count(db_session, Restaurant)

    await seed(db_session)

    assert await _count(db_session, Restaurant) == first
    assert await _count(db_session, User) == 1


@pytest.mark.asyncio
async def test_seeded_data_spans_several_cities_and_cuisines(db_session):
    """Discovery features need variety to be worth looking at."""
    await seed(db_session)

    rows = list(await db_session.execute(select(Restaurant.city, Restaurant.cuisine)))
    assert len({city for city, _ in rows}) >= 3
    assert len({cuisine for _, cuisine in rows if cuisine}) >= 4

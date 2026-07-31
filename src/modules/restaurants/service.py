"""Business logic for restaurant profiles."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.restaurants.models import Restaurant
from src.modules.restaurants.schemas import RestaurantCreate, RestaurantUpdate
from src.modules.users.models import User


async def create_restaurant(session: AsyncSession, owner: User, data: RestaurantCreate) -> Restaurant:
    restaurant = Restaurant(owner_id=owner.id, **data.model_dump())
    session.add(restaurant)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


async def get_restaurant(session: AsyncSession, restaurant_id: int) -> Restaurant:
    restaurant = await session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise NotFoundException("Restaurant", str(restaurant_id))
    return restaurant


# Shortest term that earns a suggestion lookup — one character matches most of
# the table and is never a useful hint.
SUGGEST_MIN_CHARS = 2


def _matches_term(term: str):
    """Name-or-cuisine predicate shared by browse and suggest.

    Both paths use it so a suggestion can never appear that pressing Search
    then fails to return. `cuisine` is nullable, but `NULL ILIKE x` is NULL
    rather than true, so untagged restaurants drop out without a COALESCE.
    """
    pattern = f"%{term}%"
    return or_(Restaurant.name.ilike(pattern), Restaurant.cuisine.ilike(pattern))


async def list_restaurants(
    session: AsyncSession, city: str | None = None, search: str | None = None
) -> list[Restaurant]:
    stmt = select(Restaurant)
    if city and city.strip():
        # Case-insensitive and partial, matching how the name field behaves —
        # both are free-text inputs, so "metro" should find "Metropolis".
        stmt = stmt.where(Restaurant.city.ilike(f"%{city.strip()}%"))
    if search and search.strip():
        stmt = stmt.where(_matches_term(search.strip()))
    stmt = stmt.order_by(Restaurant.name)
    return list(await session.scalars(stmt))


async def suggest_restaurants(
    session: AsyncSession, q: str, limit: int = 8
) -> list[Restaurant]:
    """Typeahead hits for a partial query. Empty below SUGGEST_MIN_CHARS."""
    term = (q or "").strip()
    if len(term) < SUGGEST_MIN_CHARS:
        return []
    stmt = (
        select(Restaurant)
        .where(_matches_term(term))
        .order_by(Restaurant.name)
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def popular_cuisines(session: AsyncSession, limit: int = 8) -> list[tuple[str, int]]:
    """Cuisines by restaurant count, busiest first.

    Ties break on name so the ordering is deterministic and tests are stable.
    """
    count = func.count(Restaurant.id)
    stmt = (
        select(Restaurant.cuisine, count)
        .where(Restaurant.cuisine.isnot(None), Restaurant.cuisine != "")
        .group_by(Restaurant.cuisine)
        .order_by(count.desc(), Restaurant.cuisine)
        .limit(limit)
    )
    return [(cuisine, total) for cuisine, total in await session.execute(stmt)]


async def owned_restaurant(session: AsyncSession, user: User, restaurant_id: int) -> Restaurant:
    """Return the restaurant if the user may manage it, else raise.

    404 if it doesn't exist; 403 if it exists but the user is neither the owner
    nor an admin.
    """
    restaurant = await get_restaurant(session, restaurant_id)
    if restaurant.owner_id != user.id and user.role != "admin":
        raise ForbiddenException("You do not manage this restaurant")
    return restaurant


async def update_restaurant(
    session: AsyncSession, restaurant_id: int, user: User, data: RestaurantUpdate
) -> Restaurant:
    restaurant = await owned_restaurant(session, user, restaurant_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(restaurant, field, value)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant

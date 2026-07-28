"""Business logic for restaurant profiles."""

from sqlalchemy import select
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


async def list_restaurants(
    session: AsyncSession, city: str | None = None, search: str | None = None
) -> list[Restaurant]:
    stmt = select(Restaurant)
    if city:
        stmt = stmt.where(Restaurant.city == city)
    if search:
        stmt = stmt.where(Restaurant.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Restaurant.name)
    return list(await session.scalars(stmt))


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

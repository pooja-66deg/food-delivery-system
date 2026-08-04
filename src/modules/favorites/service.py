"""Saving and listing a customer's favourite restaurants."""
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.favorites.models import Favorite
from src.modules.restaurants import service as restaurant_service
from src.modules.restaurants.models import Restaurant


async def add(session: AsyncSession, user_id: int, restaurant_id: int) -> Favorite:
    """Favourite a restaurant. Idempotent — favouriting twice is not an error.

    404s on an unknown restaurant rather than storing a dangling favourite. The
    duplicate is caught from the unique constraint instead of by checking first,
    so two concurrent taps cannot both pass the check and then both insert.
    """
    await restaurant_service.get_restaurant(session, restaurant_id)  # 404 if gone

    favorite = Favorite(user_id=user_id, restaurant_id=restaurant_id)
    session.add(favorite)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(Favorite).where(
                Favorite.user_id == user_id, Favorite.restaurant_id == restaurant_id
            )
        )
        if existing is None:
            raise
        return existing
    await session.refresh(favorite)
    return favorite


async def remove(session: AsyncSession, user_id: int, restaurant_id: int) -> bool:
    """Un-favourite. Returns whether a row was removed.

    Scoped to the caller, so one user can never clear another's favourites.
    """
    result = await session.execute(
        delete(Favorite).where(
            Favorite.user_id == user_id, Favorite.restaurant_id == restaurant_id
        )
    )
    await session.commit()
    return bool(result.rowcount)


async def list_restaurants(
    session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> list[Restaurant]:
    """The user's favourite restaurants, most recently saved first."""
    stmt = (
        select(Restaurant)
        .join(Favorite, Favorite.restaurant_id == Restaurant.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt))


async def restaurant_ids(session: AsyncSession, user_id: int) -> list[int]:
    """Just the ids, for a client marking which browse cards are saved."""
    stmt = (
        select(Favorite.restaurant_id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.id.desc())
    )
    return list(await session.scalars(stmt))

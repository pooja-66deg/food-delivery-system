"""A customer's saved restaurants.

The storage lives here because every read of it is "my favourites" — it is a
fact about a user, not about a restaurant.

What changed in the split: the monolith's ``GET /favorites`` returned full
restaurant cards, joining the restaurants table and attaching ratings and price
bands. This database has no restaurants table, and hydrating them here would
mean calling the restaurants service on a page that is otherwise entirely local.

So the split is by ownership: this service answers *which* restaurants, the
restaurants service answers *what they are* (``GET /restaurants?ids=``). Two
calls, each served entirely by the service that owns the data, and a slow
restaurants service degrades the favourites page instead of breaking it.
"""

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import current_user
from app.models import Favorite, User
from shared.errors import ForbiddenException, NotFoundException
from shared.ids import BodyId, EntityId, INT64_MAX

router = APIRouter(prefix="/favorites", tags=["favorites"])


async def _customer(user: User = Depends(current_user)) -> User:
    """The signed-in customer, checked against the database rather than the token.

    These four routes used ``auth.require_role("customer")``, which decodes the
    JWT and compares the role claim — and nothing else. It was the only place in
    this service not going through ``current_user``, so it was also the only
    place that skipped the revocation blocklist, the ``is_active`` check and the
    session-generation check. A token that had been logged out still read and
    wrote favourites; so did a deactivated account's, and one issued before a
    password reset.

    Every other authenticated route here has the user row in front of it and
    checks all three. The staleness window other services accept exists because
    they cannot see that row without a network call. This service can.
    """
    if user.role != "customer":
        raise ForbiddenException("Insufficient permissions")
    return user


class FavoriteCreate(BaseModel):
    restaurant_id: BodyId


@router.get("/ids", response_model=list[int])
async def list_my_favorite_ids(
    caller: User = Depends(_customer), session: AsyncSession = Depends(get_db)
):
    """The saved restaurant ids, most recently saved first.

    Also what a browse page uses to mark which cards are already saved, without
    fetching every favourite in full.
    """
    return await restaurant_ids(session, caller.id)


@router.get("", response_model=list[int])
async def list_my_favorites(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    caller: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    """Saved restaurant ids, paged. Hydrate them via ``GET /restaurants?ids=``."""
    stmt = (
        select(Favorite.restaurant_id)
        .where(Favorite.user_id == caller.id)
        .order_by(Favorite.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt))


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(
    data: FavoriteCreate,
    caller: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    """Save a restaurant. Idempotent, so a double tap is not an error.

    Note what is *not* checked: whether the restaurant exists. That is the
    restaurants service's fact, and asking it would make saving a favourite fail
    whenever it is down. A favourite pointing at a deleted restaurant simply
    does not hydrate, which the list already has to cope with.
    """
    await add(session, caller.id, data.restaurant_id)


@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    restaurant_id: EntityId,
    caller: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    if not await remove(session, caller.id, restaurant_id):
        raise NotFoundException("Favorite", str(restaurant_id))


async def add(session: AsyncSession, user_id: int, restaurant_id: int) -> None:
    """Favourite a restaurant. Idempotent — favouriting twice is not an error.

    Leans on the unique constraint rather than checking first, so two concurrent
    taps cannot both slip through the gap between the check and the insert.
    """
    session.add(Favorite(user_id=user_id, restaurant_id=restaurant_id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


async def remove(session: AsyncSession, user_id: int, restaurant_id: int) -> bool:
    """Unfavourite. Returns whether anything was removed."""
    result = await session.execute(
        delete(Favorite).where(
            Favorite.user_id == user_id, Favorite.restaurant_id == restaurant_id
        )
    )
    await session.commit()
    return bool(result.rowcount)


async def restaurant_ids(session: AsyncSession, user_id: int) -> list[int]:
    stmt = (
        select(Favorite.restaurant_id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.id.desc())
    )
    return list(await session.scalars(stmt))

"""HTTP routes for favourite restaurants."""
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database import get_db
from src.core.exceptions import NotFoundException
from src.modules.favorites import service
from src.modules.restaurants import discovery
from src.modules.restaurants import service as restaurant_service
from src.modules.restaurants.schemas import RestaurantResponse
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/favorites", tags=["favorites"])

# Favourites are a customer's shortlist; owners and drivers have no use for one.
_customer = require_role("customer")


class FavoriteCreate(BaseModel):
    restaurant_id: int


@router.get("", response_model=list[RestaurantResponse])
async def list_my_favorites(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    """Saved restaurants, most recently saved first — with the same rating and
    price detail the browse cards carry, so the list renders identically."""
    found = await service.list_restaurants(session, user.id, limit, offset)
    await restaurant_service.attach_ratings(session, found)
    await discovery.attach_price_bands(session, found)
    await discovery.attach_matched_items(session, found, None)
    return found


@router.get("/ids", response_model=list[int])
async def list_my_favorite_ids(
    user: User = Depends(_customer), session: AsyncSession = Depends(get_db)
):
    """Ids only, so a browse page can mark which cards are already saved without
    fetching every favourite in full."""
    return await service.restaurant_ids(session, user.id)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(
    data: FavoriteCreate,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    """Save a restaurant. Idempotent, so a double tap is not an error."""
    await service.add(session, user.id, data.restaurant_id)


@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    restaurant_id: int,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    if not await service.remove(session, user.id, restaurant_id):
        raise NotFoundException("Favorite", str(restaurant_id))

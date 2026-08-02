"""HTTP routes for the restaurants domain.

Public: browse restaurants and view menus.
Owner (role restaurant/admin): create/update restaurants and manage menus.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.adapters.database import get_db
from src.modules.restaurants import menu as menu_service
from src.modules.restaurants import service
from src.modules.restaurants.models import MenuItem
from src.modules.restaurants.storage import save_image
from src.modules.restaurants.schemas import (
    CategoryCreate,
    CategoryResponse,
    CuisineCount,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
    RestaurantCreate,
    RestaurantDetail,
    RestaurantResponse,
    RestaurantSuggestion,
    RestaurantUpdate,
)
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

# Only restaurant owners (or admins) may manage restaurants and menus.
owner_only = require_role("restaurant", "admin")


# ---------- Public browsing ----------
@router.get("", response_model=list[RestaurantResponse])
async def list_restaurants(
    city: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await service.list_restaurants(session, city=city, search=search)


# ---------- Discovery ----------
# These MUST stay above `/{restaurant_id}`. FastAPI resolves routes in
# declaration order and does not fall through when a path parameter fails type
# conversion, so declaring "/suggest" later makes it 422 on `int("suggest")`
# instead of reaching this handler. Covered by
# test_suggest_route_resolves_before_restaurant_id.
@router.get("/suggest", response_model=list[RestaurantSuggestion])
async def suggest(
    q: str = Query(..., description="Partial restaurant name or cuisine"),
    limit: int = Query(default=8, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
):
    return await service.suggest_restaurants(session, q, limit=limit)


@router.get("/cuisines/popular", response_model=list[CuisineCount])
async def popular_cuisines(
    limit: int = Query(default=8, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
):
    rows = await service.popular_cuisines(session, limit=limit)
    return [CuisineCount(cuisine=cuisine, count=count) for cuisine, count in rows]


@router.get("/{restaurant_id}", response_model=RestaurantDetail)
async def get_restaurant(restaurant_id: int, session: AsyncSession = Depends(get_db)):
    restaurant = await service.get_restaurant(session, restaurant_id)
    menu = await menu_service.get_menu(session, restaurant_id, available_only=True)
    detail = RestaurantDetail.model_validate(restaurant)
    detail.menu = menu
    return detail


# ---------- Owner: restaurant profile ----------
@router.post("", response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    data: RestaurantCreate,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    return await service.create_restaurant(session, user, data)


@router.patch("/{restaurant_id}", response_model=RestaurantResponse)
async def update_restaurant(
    restaurant_id: int,
    data: RestaurantUpdate,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    return await service.update_restaurant(session, restaurant_id, user, data)


@router.post("/{restaurant_id}/image", response_model=RestaurantResponse)
async def upload_restaurant_image(
    restaurant_id: int,
    file: UploadFile = File(...),
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    restaurant = await service.owned_restaurant(session, user, restaurant_id)
    restaurant.image_url = await save_image(file, f"restaurants/{restaurant_id}")
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


# ---------- Menu: categories ----------
@router.get("/{restaurant_id}/categories", response_model=list[CategoryResponse])
async def list_categories(restaurant_id: int, session: AsyncSession = Depends(get_db)):
    return await menu_service.list_categories(session, restaurant_id)


@router.post(
    "/{restaurant_id}/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def add_category(
    restaurant_id: int,
    data: CategoryCreate,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.add_category(session, user, restaurant_id, data)


# ---------- Menu: items ----------
@router.post(
    "/{restaurant_id}/items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_item(
    restaurant_id: int,
    data: MenuItemCreate,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.add_item(session, user, restaurant_id, data)


@router.patch("/{restaurant_id}/items/{item_id}", response_model=MenuItemResponse)
async def update_item(
    restaurant_id: int,
    item_id: int,
    data: MenuItemUpdate,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.update_item(session, user, restaurant_id, item_id, data)


@router.delete("/{restaurant_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    restaurant_id: int,
    item_id: int,
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    await menu_service.delete_item(session, user, restaurant_id, item_id)


@router.post("/{restaurant_id}/items/{item_id}/image", response_model=MenuItemResponse)
async def upload_item_image(
    restaurant_id: int,
    item_id: int,
    file: UploadFile = File(...),
    user: User = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    await service.owned_restaurant(session, user, restaurant_id)  # authz
    item = await session.get(MenuItem, item_id)
    if item is None or item.restaurant_id != restaurant_id:
        raise NotFoundException("Menu item", str(item_id))
    item.image_url = await save_image(file, f"restaurants/{restaurant_id}/items")
    await session.commit()
    await session.refresh(item)
    return item

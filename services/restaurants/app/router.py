"""HTTP routes for the restaurants domain.

Public: browse restaurants and view menus. Browse shows approved venues only.
Owner (role restaurant): register and manage their own restaurant and its menu.
Admin: list every venue whatever its status, and approve or reject one.

The split between the last two is the point. An admin may *not* register a
restaurant — owners do that for themselves, and an operator who could create one
would be creating a venue with no one to run it. What an admin can do is decide
whether a registered venue trades, which is what ``owner_or_admin`` versus
``owner_only`` versus ``admin_only`` below encode.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundException
from app.db import get_db
from app import discovery
from app import menu as menu_service
from app import service
from app.models import APPROVED, MenuItem
from app.storage import save_image
from app.schemas import (
    AdminRestaurantPage,
    AdminRestaurantRow,
    ApprovalDecision,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    CuisineCount,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
    RestaurantCreate,
    RestaurantDetail,
    RestaurantPage,
    RestaurantResponse,
    RestaurantSuggestion,
    RestaurantUpdate,
)
from app.auth import auth
from shared.identity import Identity
from shared.ids import EntityId, INT64_MAX

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

# Managing an existing restaurant and its menu. Admin is included because an
# operator sometimes has to correct a listing; service.owned_restaurant() is
# what still stops one owner touching another's.
owner_or_admin = auth.require_role("restaurant", "admin")

# Registering a new restaurant. Deliberately narrower than owner_or_admin:
# admins are excluded, because a venue an operator created would have no owner
# to run it and no one to hold the one-restaurant-per-account rule against.
owner_only = auth.require_role("restaurant")

# Deciding whether a venue trades. Only ever an operator.
admin_only = auth.require_role("admin")

# The public detail route answers for anyone, but shows an unapproved venue only
# to its owner or an operator — so the caller is resolved when present and simply
# absent when not, rather than demanded.
maybe_caller = auth.maybe_identity()


# ---------- Public browsing ----------
@router.get("", response_model=RestaurantPage)
async def list_restaurants(
    city: str | None = Query(default=None),
    search: str | None = Query(
        default=None, description="Matches restaurant name, cuisine, or a dish on the menu"
    ),
    cuisine: str | None = Query(default=None),
    min_rating: float | None = Query(default=None, ge=1, le=5),
    price_band: int | None = Query(default=None, ge=1, le=discovery.MAX_PRICE_BAND),
    vegetarian_only: bool = Query(default=False),
    open_only: bool = Query(default=False),
    # Anchored: an unanchored alternation matches substrings, so "xratingx"
    # would pass validation and then silently fall back to the default sort.
    sort: str = Query(
        default=discovery.DEFAULT_SORT, pattern=f"^({'|'.join(discovery.SORTS)})$"
    ),
    limit: int = Query(default=discovery.DEFAULT_LIMIT, ge=1, le=discovery.MAX_LIMIT),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    session: AsyncSession = Depends(get_db),
):
    """Browse and search restaurants.

    Returns a page plus the total match count — see ``RestaurantPage`` for why
    this is an envelope rather than a bare list.
    """
    result = await discovery.search(
        session, city=city, search=search, cuisine=cuisine, min_rating=min_rating,
        price_band=price_band, vegetarian_only=vegetarian_only, open_only=open_only,
        sort=sort, limit=limit, offset=offset,
    )
    await service.attach_ratings(session, result.items)
    await service.attach_opening_hours(session, result.items)
    await discovery.attach_price_bands(session, result.items)
    await discovery.attach_matched_items(session, result.items, search)
    return RestaurantPage(
        items=[RestaurantResponse.model_validate(r) for r in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


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


@router.get("/cities", response_model=dict[str, list[str]])
async def get_cities(session: AsyncSession = Depends(get_db)) -> dict[str, list[str]]:
    """Return a list of all unique cities where restaurants operate."""
    cities = await service.list_cities(session)
    return {"cities": cities}


# ---------- Owner: my own restaurant ----------
# Also above `/{restaurant_id}`, for the reason given under Discovery.
@router.get("/mine", response_model=list[RestaurantResponse])
async def my_restaurants(
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    """The signed-in owner's own restaurants, whatever their approval status.

    The dashboard cannot be built from browse. Browse returns approved venues
    only, so an owner waiting on approval — or rejected — would open their
    dashboard to nothing at all and conclude the registration was lost. This is
    the endpoint that shows them their venue and why it is not yet listed.

    A list, though the platform allows one each: the shape survives the rule
    being relaxed, and the dashboard already renders a collection.
    """
    restaurants = await service.owned_by(session, user.user_id)
    await service.attach_ratings(session, restaurants)
    await service.attach_opening_hours(session, restaurants)
    return restaurants


# ---------- Admin: the operator console ----------
@router.get("/admin/all", response_model=AdminRestaurantPage)
async def admin_list_restaurants(
    approval_status: str | None = Query(
        default=None, description="Filter to one status; omit for every venue"
    ),
    limit: int = Query(default=discovery.DEFAULT_LIMIT, ge=1, le=discovery.MAX_LIMIT),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    _: Identity = Depends(admin_only),
    session: AsyncSession = Depends(get_db),
):
    """Every restaurant on the platform, for the operator console.

    Separate from browse rather than a flag on it, because the two answer
    different questions and must not share a code path: browse answers "what may
    a customer order from", and a bug that let an unapproved venue leak into it
    is exactly what the separation prevents.
    """
    result = await service.admin_list(
        session, approval_status=approval_status, limit=limit, offset=offset
    )
    await service.attach_ratings(session, result.items)
    await service.attach_opening_hours(session, result.items)
    await service.attach_owner_names(session, result.items)
    return AdminRestaurantPage(
        items=[AdminRestaurantRow.model_validate(r) for r in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


@router.post("/{restaurant_id}/approval", response_model=AdminRestaurantRow)
async def decide_approval(
    restaurant_id: EntityId,
    decision: ApprovalDecision,
    _: Identity = Depends(admin_only),
    session: AsyncSession = Depends(get_db),
):
    """Approve or reject a registered venue.

    One endpoint for both directions rather than /approve and /reject: the
    rejection reason belongs to the same decision, and a reject-then-approve
    sequence has to clear it — which is easier to get right in one place.
    """
    restaurant = await service.set_approval(
        session, restaurant_id, decision.status, decision.reason
    )
    await service.attach_ratings(session, [restaurant])
    await service.attach_opening_hours(session, [restaurant])
    await service.attach_owner_names(session, [restaurant])
    return AdminRestaurantRow.model_validate(restaurant)


@router.get("/{restaurant_id}", response_model=RestaurantDetail)
async def get_restaurant(
    restaurant_id: EntityId,
    caller: Identity | None = Depends(maybe_caller),
    session: AsyncSession = Depends(get_db),
):
    """A restaurant's public page.

    Approval-gated, which every *other* public read here already was — browse,
    search, suggest, cities and popular cuisines all filter on it (discovery.py
    calls that filter "the boundary between 'a row exists' and 'a customer may
    see it'"). This route did not, and ids are sequential, so walking them
    returned every pending applicant's venue name, street address and phone
    number to an anonymous caller.

    Two callers do have a reason to see an unapproved venue: its own owner, who
    must be able to review what they submitted, and an admin, who has to decide
    on it. Both are established from the token, so an anonymous request cannot
    claim either.
    """
    restaurant = await service.get_restaurant(session, restaurant_id)
    if restaurant.approval_status != APPROVED and not (
        caller is not None
        and (caller.role == "admin" or caller.user_id == restaurant.owner_id)
    ):
        # The same answer an absent row gets. "There is a venue here you may not
        # see" is itself the fact being withheld.
        raise NotFoundException("Restaurant", str(restaurant_id))
    await service.attach_ratings(session, [restaurant])
    await service.attach_opening_hours(session, [restaurant])
    menu = await menu_service.get_menu(session, restaurant_id, available_only=True)
    detail = RestaurantDetail.model_validate(restaurant)
    detail.menu = menu
    return detail


# ---------- Owner: restaurant profile ----------
@router.post("", response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    data: RestaurantCreate,
    user: Identity = Depends(owner_only),
    session: AsyncSession = Depends(get_db),
):
    restaurant = await service.create_restaurant(session, user, data)
    await service.attach_opening_hours(session, [restaurant])
    return restaurant


@router.patch("/{restaurant_id}", response_model=RestaurantResponse)
async def update_restaurant(
    restaurant_id: EntityId,
    data: RestaurantUpdate,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    restaurant = await service.update_restaurant(session, restaurant_id, user, data)
    await service.attach_opening_hours(session, [restaurant])
    return restaurant


@router.post("/{restaurant_id}/image", response_model=RestaurantResponse)
async def upload_restaurant_image(
    restaurant_id: EntityId,
    file: UploadFile = File(...),
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    restaurant = await service.owned_restaurant(session, user, restaurant_id)
    restaurant.image_url = await save_image(file, f"restaurants/{restaurant_id}")
    await session.commit()
    await session.refresh(restaurant)
    await service.attach_opening_hours(session, [restaurant])
    return restaurant


# ---------- Menu: categories ----------
@router.get("/{restaurant_id}/categories", response_model=list[CategoryResponse])
async def list_categories(restaurant_id: EntityId, session: AsyncSession = Depends(get_db)):
    return await menu_service.list_categories(session, restaurant_id)


@router.post(
    "/{restaurant_id}/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def add_category(
    restaurant_id: EntityId,
    data: CategoryCreate,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.add_category(session, user, restaurant_id, data)


@router.patch("/{restaurant_id}/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    restaurant_id: EntityId,
    category_id: EntityId,
    data: CategoryUpdate,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.update_category(session, user, restaurant_id, category_id, data)


@router.delete(
    "/{restaurant_id}/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_category(
    restaurant_id: EntityId,
    category_id: EntityId,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    # 409 when the category still holds items — see menu_service.delete_category.
    await menu_service.delete_category(session, user, restaurant_id, category_id)


# ---------- Menu: items ----------
@router.post(
    "/{restaurant_id}/items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_item(
    restaurant_id: EntityId,
    data: MenuItemCreate,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.add_item(session, user, restaurant_id, data)


@router.patch("/{restaurant_id}/items/{item_id}", response_model=MenuItemResponse)
async def update_item(
    restaurant_id: EntityId,
    item_id: EntityId,
    data: MenuItemUpdate,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    return await menu_service.update_item(session, user, restaurant_id, item_id, data)


@router.delete("/{restaurant_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    restaurant_id: EntityId,
    item_id: EntityId,
    user: Identity = Depends(owner_or_admin),
    session: AsyncSession = Depends(get_db),
):
    await menu_service.delete_item(session, user, restaurant_id, item_id)


@router.post("/{restaurant_id}/items/{item_id}/image", response_model=MenuItemResponse)
async def upload_item_image(
    restaurant_id: EntityId,
    item_id: EntityId,
    file: UploadFile = File(...),
    user: Identity = Depends(owner_or_admin),
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

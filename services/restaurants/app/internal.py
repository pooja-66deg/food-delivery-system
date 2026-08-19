"""Endpoints other services call, rather than browsers.

Three of them, and each exists because the alternative was worse.

``/validate-order`` is the one sync call the whole split accepts. Checkout needs
five answers that only this service can give — is the restaurant open, do these
items exist and cost what the customer was shown, is there enough stock, does it
deliver to this address, is the minimum met — and it needs the stock *reserved*
against that same answer. Two calls (ask, then reserve) would leave a race in
between where another customer takes the last portion. So it is one call, one
transaction, in the database that owns stock.

``/release-stock`` is its inverse, for a cancelled or rejected order.

``/lookup`` hydrates: a cart adding an item needs its name and price, and a
favourites list needs the cards behind a set of ids. Both used to be joins.

Mounted under the same ``/restaurants`` prefix so the gateway needs no special
case, and guarded by the caller's own token — a service calling this forwards
the end user's Authorization header rather than holding a machine credential of
its own, so the customer's identity is never lost between hops.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import hours as hours_mod
from app import inventory, zones
from app import service as restaurant_service
from app.auth import auth
from app.db import get_db
from app.models import APPROVED, MenuItem, Restaurant
from app.schemas import RestaurantResponse
from shared.errors import NotFoundException
from shared.identity import Identity
from shared.ids import EntityId, clamp_id

router = APIRouter(prefix="/restaurants", tags=["internal"])

_caller = auth.identity()


class OrderLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(..., ge=1)
    #: What the customer was shown. Compared, never trusted.
    unit_price: Decimal


class AddressPoint(BaseModel):
    """Just enough of an address to decide serviceability.

    Deliberately not the whole address: this service has no business holding a
    customer's street line, and does not need it to measure a distance.
    """

    city: str
    latitude: float | None = None
    longitude: float | None = None


class ValidateOrderRequest(BaseModel):
    items: list[OrderLine]
    address: AddressPoint
    #: False to check without taking stock — used by a "can I order this?" probe.
    reserve: bool = True


class ValidatedLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    menu_item_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class ValidateOrderResponse(BaseModel):
    ok: bool
    #: Machine-readable, matching the codes the frontend already handles:
    #: RESTAURANT_CLOSED, ITEM_OUT_OF_STOCK, PRICE_MISMATCH_REFRESH,
    #: ADDRESS_OUT_OF_ZONE, MIN_ORDER_NOT_MET.
    code: str | None = None
    message: str | None = None
    restaurant_id: int | None = None
    items: list[ValidatedLine] = []
    subtotal: Decimal = Decimal("0")


def _reject(code: str, message: str) -> ValidateOrderResponse:
    """A failed validation is a 200 with ok=false, not an HTTP error.

    These are ordinary business outcomes — a closed kitchen is not a fault — and
    the caller has to distinguish them from "the service is unreachable", which
    it retries. Encoding both as 4xx would blur exactly that line.
    """
    return ValidateOrderResponse(ok=False, code=code, message=message)


@router.post("/{restaurant_id}/validate-order", response_model=ValidateOrderResponse)
async def validate_order(
    restaurant_id: EntityId,
    body: ValidateOrderRequest,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """Validate a proposed order and, if it holds up, reserve the stock."""
    restaurant = await session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise NotFoundException("Restaurant", str(restaurant_id))

    if not restaurant.is_open:
        return _reject("RESTAURANT_CLOSED", "This restaurant is currently closed.")

    schedule = await restaurant_service.opening_hours_for(session, restaurant_id)
    # Empty schedule → is_open alone, same as before. Schedule present → both.
    if not hours_mod.schedule_status(restaurant.is_open, schedule).accepting_orders:
        return _reject("RESTAURANT_CLOSED", "This restaurant is currently closed.")

    wanted = {line.menu_item_id: line for line in body.items}
    if not wanted:
        return _reject("EMPTY_CART", "Your cart is empty.")

    rows = {
        item.id: item
        for item in await session.scalars(
            select(MenuItem).where(
                MenuItem.id.in_(wanted), MenuItem.restaurant_id == restaurant_id
            )
        )
    }

    validated: list[ValidatedLine] = []
    subtotal = Decimal("0")
    for line in body.items:
        item = rows.get(line.menu_item_id)
        if item is None or not item.is_available:
            return _reject("ITEM_OUT_OF_STOCK", "An item is no longer available.")
        if inventory.shortfall(item, line.quantity):
            return _reject(
                "ITEM_OUT_OF_STOCK",
                f"Only {item.stock_quantity} left of '{item.name}'.",
            )
        # The price the customer was shown must still be the price. Checked per
        # line rather than by hashing the cart, because this service never saw
        # the cart — the hash is the caller's concern, the truth is ours.
        if Decimal(item.price) != Decimal(line.unit_price):
            return _reject(
                "PRICE_MISMATCH_REFRESH", "Prices changed. Please review your cart."
            )
        line_total = Decimal(item.price) * line.quantity
        subtotal += line_total
        validated.append(
            ValidatedLine(
                menu_item_id=item.id,
                name=item.name,
                unit_price=item.price,
                quantity=line.quantity,
                line_total=line_total,
            )
        )

    verdict = zones.check(restaurant, body.address)
    if not verdict.serviceable:
        return _reject("ADDRESS_OUT_OF_ZONE", zones.rejection_message(restaurant, verdict))

    if subtotal < restaurant.min_order_amount:
        return _reject(
            "MIN_ORDER_NOT_MET",
            f"Minimum order is {restaurant.min_order_amount}. Add a little more.",
        )

    if body.reserve:
        # Same transaction as the checks above, so nobody can take the last
        # portion between validating and reserving it.
        await inventory.apply_order(session, validated)
        await session.commit()

    return ValidateOrderResponse(
        ok=True, restaurant_id=restaurant.id, items=validated, subtotal=subtotal
    )


class ReleaseStockRequest(BaseModel):
    items: list[OrderLine]


@router.post("/{restaurant_id}/release-stock", status_code=204)
async def release_stock(
    restaurant_id: EntityId,
    body: ReleaseStockRequest,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """Put stock back for a cancelled or rejected order.

    Idempotent in the direction that matters: replaying it over-credits stock,
    which an owner can correct, where losing it leaves food nobody can order.
    """
    await inventory.restore_order(session, body.items)
    await session.commit()


class MenuItemLookup(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    restaurant_id: int
    name: str
    price: Decimal
    is_available: bool
    stock_quantity: int | None


def _wanted_ids(ids: str) -> list[int]:
    """The usable ids in a comma-separated list.

    ``clamp_id`` drops anything outside int32 rather than letting it reach the
    query, where asyncpg raised while binding an int4 and turned the whole batch
    into a 500. One unusable id should cost the caller that id, not the results
    for the others.
    """
    parsed = (int(i) for i in ids.split(",") if i.strip().lstrip("-").isdigit())
    return [i for i in (clamp_id(v) for v in parsed) if i is not None]


@router.get("/items/lookup", response_model=list[MenuItemLookup])
async def lookup_items(
    ids: str = Query(..., description="Comma-separated menu item ids"),
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """Name and price for a set of menu items.

    What the cart uses when an item is added, so the cart can then render
    entirely from its own store instead of asking again on every read.

    Guarded like the rest of this file. It was not, and the module docstring's
    claim that these endpoints are "guarded by the caller's own token" was
    therefore false for exactly the two routes that read data out.
    """
    wanted = _wanted_ids(ids)
    if not wanted:
        return []
    return list(await session.scalars(select(MenuItem).where(MenuItem.id.in_(wanted))))


@router.get("/lookup", response_model=list[RestaurantResponse])
async def lookup_restaurants(
    ids: str = Query(..., description="Comma-separated restaurant ids"),
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    """The cards behind a set of restaurant ids.

    Hydrates a favourites list, which lives in the users service and can only
    store ids. Was a join; is now one call to the service that owns the answer.

    Approved venues only, and authenticated. Unguarded and unfiltered, this
    answered for *any* id to *anyone*: an anonymous caller could walk
    ``?ids=1,2,3`` and read every pending applicant's venue name, street address
    and phone number — the owner's contact details, before an operator had even
    reviewed the application. A favourites list only ever holds venues the
    customer could see in the first place, so the filter costs it nothing.
    """
    wanted = _wanted_ids(ids)
    if not wanted:
        return []
    found = list(await session.scalars(
        select(Restaurant).where(
            Restaurant.id.in_(wanted),
            Restaurant.approval_status == APPROVED,
        )
    ))
    # Same rating detail the browse cards carry, so the list renders identically.
    await restaurant_service.attach_ratings(session, found)
    await restaurant_service.attach_opening_hours(session, found)
    return found

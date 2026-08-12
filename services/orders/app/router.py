"""HTTP surface: orders and the cart.

Same paths and shapes as the monolith's two routers, so the frontend does not
know they moved. Guards take ``Identity`` — an id and a role, which is all these
routes ever used.

The one place a token is passed further than the guard is checkout: it forwards
the caller's own Authorization header to the restaurants service, so that service
authorises the same person rather than trusting a machine credential.
"""

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import cart as cart_service
from app import service
from app.auth import auth
from app import reorder as reorder_service
from app.cart_schemas import (
    AddToCart, CartView, CheckoutRequest, ReorderRequest, ReorderResponse,
    UpdateCartItem,
)
from app.db import get_db
from app.models import OrderStatus
from app.redis_client import get_redis
from app.schemas import OrderRead, OrderSummary
from shared.identity import Identity
from shared.ids import EntityId, INT64_MAX

router = APIRouter(prefix="/orders", tags=["orders"])
cart_router = APIRouter(prefix="/cart", tags=["cart"])

_customer = auth.require_role("customer")
_restaurant = auth.require_role("restaurant", "admin")
_admin = auth.require_role("admin")
_caller = auth.identity()


class RejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class StatusBody(BaseModel):
    status: OrderStatus


# --------------------------------------------------------------------------
# Cart
# --------------------------------------------------------------------------


@cart_router.get("", response_model=CartView)
async def view_cart(user: Identity = Depends(_customer), redis=Depends(get_redis)):
    return await cart_service.get_cart(redis, user.user_id)


@cart_router.post("/items", response_model=CartView)
async def add_to_cart(
    data: AddToCart,
    user: Identity = Depends(_customer),
    redis=Depends(get_redis),
    authorization: str | None = Header(default=None),
):
    return await cart_service.add_item(
        redis, user.user_id, data.menu_item_id, data.quantity, authorization or ""
    )


@cart_router.patch("/items/{menu_item_id}", response_model=CartView)
async def update_cart_item(
    menu_item_id: EntityId,
    data: UpdateCartItem,
    user: Identity = Depends(_customer),
    redis=Depends(get_redis),
):
    return await cart_service.update_item(redis, user.user_id, menu_item_id, data.quantity)


@cart_router.post("/reorder", response_model=ReorderResponse)
async def reorder(
    data: ReorderRequest,
    user: Identity = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    authorization: str | None = Header(default=None),
):
    """Refill the cart from a past order, reporting what could not be carried."""
    result = await reorder_service.reorder(
        redis, session, user, data.order_id, authorization or ""
    )
    return ReorderResponse(cart=result.cart, skipped=result.skipped)


@cart_router.delete("/items/{menu_item_id}", response_model=CartView)
async def remove_cart_item(
    menu_item_id: EntityId, user: Identity = Depends(_customer), redis=Depends(get_redis)
):
    return await cart_service.remove_item(redis, user.user_id, menu_item_id)


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout(
    data: CheckoutRequest,
    user: Identity = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    authorization: str | None = Header(default=None),
):
    return await service.create_order_from_checkout(
        redis, session, user, data, authorization or ""
    )


@router.get("", response_model=list[OrderSummary])
async def list_my_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    scope: str = "all",
    user: Identity = Depends(_customer),
    session: AsyncSession = Depends(get_db),
):
    return await service.list_orders(session, user.user_id, limit, offset, scope)


@router.get("/restaurant/{restaurant_id}", response_model=list[OrderRead])
async def restaurant_orders(
    restaurant_id: EntityId,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    user: Identity = Depends(_restaurant),
    session: AsyncSession = Depends(get_db),
):
    return await service.list_orders_for_restaurant(session, user, restaurant_id, limit, offset)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: EntityId,
    user: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    return await service.get_order_for_user(session, user, order_id)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: EntityId,
    user: Identity = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    return await service.cancel_by_customer(session, user, order_id, authorization or "")


@router.post("/{order_id}/accept", response_model=OrderRead)
async def accept_order(
    order_id: EntityId,
    user: Identity = Depends(_restaurant),
    session: AsyncSession = Depends(get_db),
):
    return await service.accept_by_restaurant(session, user, order_id)


@router.post("/{order_id}/reject", response_model=OrderRead)
async def reject_order(
    order_id: EntityId,
    body: RejectBody = RejectBody(),
    user: Identity = Depends(_restaurant),
    session: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    return await service.reject_by_restaurant(
        session, user, order_id, body.reason, authorization or ""
    )


@router.post("/{order_id}/status", response_model=OrderRead)
async def set_status(
    order_id: EntityId,
    body: StatusBody,
    user: Identity = Depends(_restaurant),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.advance_status(session, user, order_id, body.status, redis=redis)


@router.post("/internal/expire-acceptances")
async def expire_acceptances(
    user: Identity = Depends(_admin), session: AsyncSession = Depends(get_db)
):
    from datetime import datetime, timezone

    expired = await service.expire_pending_acceptances(session, datetime.now(timezone.utc))
    return {"expired": expired}


@router.post("/internal/expire-unpaid")
async def expire_unpaid(
    user: Identity = Depends(_admin), session: AsyncSession = Depends(get_db)
):
    from datetime import datetime, timezone

    expired = await service.expire_unpaid_orders(session, datetime.now(timezone.utc))
    return {"expired": expired}

"""HTTP routes for the cart & checkout domain. All routes are per-authenticated-user."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database import get_db
from src.adapters.redis import get_redis
from src.modules.cart import checkout as checkout_service
from src.modules.cart import reorder as reorder_service
from src.modules.cart import service as cart_service
from src.modules.cart.schemas import (
    AddToCart,
    CartView,
    CheckoutRequest,
    ReorderRequest,
    ReorderResponse,
    UpdateCartItem,
    ValidatedOrder,
)
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/cart", tags=["cart"])

# A cart belongs to a customer; owners/drivers/admins have no cart.
_customer = require_role("customer")


@router.get("", response_model=CartView)
async def get_cart(
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await cart_service.get_cart(redis, session, user.id)


@router.post("/items", response_model=CartView)
async def add_item(
    data: AddToCart,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await cart_service.add_item(redis, session, user.id, data.menu_item_id, data.quantity)


@router.patch("/items/{menu_item_id}", response_model=CartView)
async def update_item(
    menu_item_id: int,
    data: UpdateCartItem,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await cart_service.update_item(redis, session, user.id, menu_item_id, data.quantity)


@router.delete("/items/{menu_item_id}", response_model=CartView)
async def remove_item(
    menu_item_id: int,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await cart_service.remove_item(redis, session, user.id, menu_item_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(user: User = Depends(_customer), redis=Depends(get_redis)):
    await cart_service.clear_cart(redis, user.id)


@router.post("/reorder", response_model=ReorderResponse)
async def reorder(
    data: ReorderRequest,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Refill the cart from a past order, replacing whatever is in it.

    Succeeds even when some lines can no longer be ordered; those come back in
    ``skipped`` so the customer sees what is missing before paying.
    """
    result = await reorder_service.reorder(redis, session, user, data.order_id)
    return ReorderResponse(cart=result.cart, skipped=result.skipped)


@router.post("/checkout", response_model=ValidatedOrder)
async def checkout(
    data: CheckoutRequest,
    user: User = Depends(_customer),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await checkout_service.validate_checkout(redis, session, user, data)

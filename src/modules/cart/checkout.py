"""Checkout validation pipeline (blueprint §15).

Runs an ordered set of gates and rejects at the first failure with a machine
code the client can act on. On success it produces a ``ValidatedOrder`` — a
priced, snapshotted draft the Order domain (M4) turns into a real order.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppException, NotFoundException
from src.modules.cart import service as cart_service
from src.modules.cart.schemas import CheckoutRequest, ValidatedOrder, ValidatedOrderItem
from src.modules.restaurants.models import MenuItem
from src.modules.restaurants.service import get_restaurant
from src.modules.users.models import Address, User


class CheckoutError(AppException):
    """A checkout gate failed. ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message, status_code=422, details={"code": code})
        self.code = code


async def validate_checkout(
    redis: Redis, session: AsyncSession, user: User, request: CheckoutRequest
) -> ValidatedOrder:
    cart = await cart_service.get_cart(redis, session, user.id)

    # 0. Cart must have contents.
    if not cart.items or cart.restaurant_id is None:
        raise CheckoutError("EMPTY_CART", "Your cart is empty.")

    restaurant = await get_restaurant(session, cart.restaurant_id)

    # 1. Restaurant open?
    if not restaurant.is_open:
        raise CheckoutError("RESTAURANT_CLOSED", "This restaurant is currently closed.")

    # 2. All items still available?
    rows = {
        m.id: m
        for m in await _items_by_ids(session, [i.menu_item_id for i in cart.items])
    }
    for line in cart.items:
        item = rows.get(line.menu_item_id)
        if item is None or not item.is_available:
            raise CheckoutError("ITEM_OUT_OF_STOCK", f"'{line.name}' is no longer available.")

    # 3. Prices unchanged since the customer last saw them?
    if request.price_hash != cart.price_hash:
        raise CheckoutError("PRICE_MISMATCH_REFRESH", "Prices changed. Please review your cart.")

    # 4. Delivery address serviceable? (MVP zone = same city as the restaurant)
    address = await session.get(Address, request.address_id)
    if address is None or address.user_id != user.id:
        raise NotFoundException("Address", str(request.address_id))
    if address.city != restaurant.city:
        raise CheckoutError("ADDRESS_OUT_OF_ZONE", "We don't deliver to this address yet.")

    # 5. Minimum order value met?
    if cart.subtotal < restaurant.min_order_amount:
        raise CheckoutError(
            "MIN_ORDER_NOT_MET",
            f"Minimum order is {restaurant.min_order_amount}. Add a little more.",
        )

    return ValidatedOrder(
        restaurant_id=restaurant.id,
        address_id=address.id,
        subtotal=cart.subtotal,
        items=[
            ValidatedOrderItem(
                menu_item_id=i.menu_item_id,
                name=i.name,
                unit_price=i.unit_price,
                quantity=i.quantity,
                line_total=i.line_total,
            )
            for i in cart.items
        ],
    )


async def _items_by_ids(session: AsyncSession, ids: list[int]) -> list[MenuItem]:
    from sqlalchemy import select

    return list(await session.scalars(select(MenuItem).where(MenuItem.id.in_(ids))))

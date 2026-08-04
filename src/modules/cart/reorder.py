"""Rebuild a cart from a past order.

Ordering the same thing again is the commonest thing a returning customer wants,
and doing it by hand means finding the restaurant and re-adding every line.

The awkward part is that a past order is a snapshot and the menu has moved on:
items get delisted, sell out, or change price. So this is deliberately a
best-effort refill that *reports what it could not take* rather than either
failing the whole reorder over one missing side dish or silently handing back a
different order than the customer asked for. Price changes are not skips — the
new price is simply what it now costs, and the checkout price-hash gate already
makes the customer confirm the total before paying.
"""
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException
from src.modules.cart import service as cart_service
from src.modules.cart.schemas import CartView
from src.modules.orders import service as order_service
from src.modules.orders.models import OrderItem
from src.modules.restaurants import inventory
from src.modules.restaurants.models import MenuItem

# Why a line could not be carried over, in words the customer can act on.
UNAVAILABLE = "no longer on the menu"
SOLD_OUT = "sold out"


@dataclass
class ReorderResult:
    cart: CartView
    # Lines that could not be added, as "name — reason".
    skipped: list[str] = field(default_factory=list)


async def reorder(
    redis: Redis, session: AsyncSession, user, order_id: int
) -> ReorderResult:
    """Replace the cart with what can still be ordered from ``order_id``.

    Access follows the order's own visibility rules, then narrows to the
    customer: an owner who can *see* an order has no cart to put it in.
    """
    order = await order_service.get_order_for_user(session, user, order_id)  # 403/404
    if order.customer_id != user.id:
        raise ConflictException("Only the customer who placed an order can reorder it")

    lines = list(await session.scalars(select(OrderItem).where(OrderItem.order_id == order_id)))
    if not lines:
        raise ConflictException("That order has no items to reorder")

    current = {
        item.id: item
        for item in await session.scalars(
            select(MenuItem).where(MenuItem.id.in_([line.menu_item_id for line in lines]))
        )
    }

    # Start from empty rather than adding to whatever is in the cart: "order this
    # again" means this order, not this order plus yesterday's leftovers. It also
    # sidesteps the one-restaurant-per-cart conflict entirely.
    await cart_service.clear_cart(redis, user.id)

    skipped: list[str] = []
    for line in lines:
        item = current.get(line.menu_item_id)
        if item is None or not item.is_available:
            skipped.append(f"{line.name} — {UNAVAILABLE}")
            continue
        if inventory.shortfall(item, line.quantity):
            skipped.append(f"{line.name} — {SOLD_OUT}")
            continue
        await cart_service.add_item(redis, session, user.id, item.id, line.quantity)

    cart = await cart_service.get_cart(redis, session, user.id)
    return ReorderResult(cart=cart, skipped=skipped)

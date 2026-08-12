"""Rebuild a cart from a past order.

Ordering the same thing again is the commonest thing a returning customer wants,
and doing it by hand means finding the restaurant and re-adding every line.

The awkward part is that a past order is a snapshot and the menu has moved on:
items get delisted, sell out, or change price. So this is deliberately a
best-effort refill that *reports what it could not take* rather than either
failing the whole reorder over one missing side dish or silently handing back a
different order than the customer asked for. Price changes are not skips — the
new price is what it now costs, and the checkout price-hash gate already makes
the customer confirm the total before paying.

What changed in the split: availability and stock used to be read from the menu
table in the same query. There is no menu table here, so the lines are looked up
in one call to the restaurants service — one call for the whole order, not one
per line, because a ten-item reorder should not be ten round trips.
"""

from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cart as cart_service
from app import service as order_service
from app.cart_schemas import CartView
from app.clients import restaurants
from app.models import OrderItem
from shared.errors import ConflictException

# Why a line could not be carried over, in words the customer can act on.
UNAVAILABLE = "no longer on the menu"
SOLD_OUT = "sold out"


@dataclass
class ReorderResult:
    cart: CartView
    # Lines that could not be added, as "name — reason".
    skipped: list[str] = field(default_factory=list)


def _short(item: dict, quantity: int) -> bool:
    """True if ``quantity`` cannot be met from what is left.

    Untracked stock (null) is not short, it is unknown — the same rule the
    restaurants service applies, restated here because this is the one place
    orders has to reason about someone else's stock.
    """
    left = item.get("stock_quantity")
    return left is not None and left < quantity


async def reorder(
    redis: Redis, session: AsyncSession, user, order_id: int, auth_header: str
) -> ReorderResult:
    """Replace the cart with what can still be ordered from ``order_id``."""
    order = await order_service.get_order_for_user(session, user, order_id)  # 403/404
    if order.customer_id != user.user_id:
        raise ConflictException("Only the customer who placed an order can reorder it")

    lines = list(
        await session.scalars(select(OrderItem).where(OrderItem.order_id == order_id))
    )
    if not lines:
        raise ConflictException("That order has no items to reorder")

    # Required, not best-effort: a failed lookup used to read as an empty one,
    # which reported every line of the order as unavailable and cleared the cart
    # on the way. Better to say the reorder could not be done than to say the
    # restaurant stopped selling everything.
    rows = await restaurants().get_json(
        "/restaurants/items/lookup",
        params={"ids": ",".join(str(line.menu_item_id) for line in lines)},
        auth_header=auth_header,
    )
    current = {item["id"]: item for item in rows}

    # Start from empty rather than adding to whatever is in the cart: "order this
    # again" means this order, not this order plus yesterday's leftovers. It also
    # sidesteps the one-restaurant-per-cart conflict entirely.
    await cart_service.clear_cart(redis, user.user_id)

    skipped: list[str] = []
    for line in lines:
        item = current.get(line.menu_item_id)
        if item is None or not item.get("is_available", False):
            skipped.append(f"{line.name} — {UNAVAILABLE}")
            continue
        if _short(item, line.quantity):
            skipped.append(f"{line.name} — {SOLD_OUT}")
            continue
        await cart_service.add_item(
            redis, user.user_id, item["id"], line.quantity, auth_header
        )

    return ReorderResult(cart=await cart_service.get_cart(redis, user.user_id), skipped=skipped)

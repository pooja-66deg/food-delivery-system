"""Redis-backed shopping cart.

A cart belongs to one customer and holds items from a single restaurant. The
authoritative item names/prices are always read fresh from the database when
building a view, so stale Redis data can never drive pricing.
"""

import hashlib
import json
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, NotFoundException
from src.modules.cart.schemas import CartItemView, CartView
from src.modules.restaurants.models import MenuItem

_CART_KEY = "cart:{user_id}"
_TTL_SECONDS = 60 * 60 * 24  # carts expire after a day of inactivity


def _key(user_id: int) -> str:
    return _CART_KEY.format(user_id=user_id)


async def _load(redis: Redis, user_id: int) -> dict:
    raw = await redis.get(_key(user_id))
    if not raw:
        return {"restaurant_id": None, "items": {}}
    return json.loads(raw)


async def _save(redis: Redis, user_id: int, data: dict) -> None:
    await redis.set(_key(user_id), json.dumps(data), ex=_TTL_SECONDS)


def _price_hash(items: list[CartItemView]) -> str:
    payload = ";".join(f"{i.menu_item_id}:{i.unit_price}" for i in sorted(items, key=lambda x: x.menu_item_id))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _build_view(session: AsyncSession, data: dict) -> CartView:
    quantities: dict[str, int] = data.get("items", {})
    if not quantities:
        return CartView()

    ids = [int(i) for i in quantities]
    rows = {m.id: m for m in await session.scalars(select(MenuItem).where(MenuItem.id.in_(ids)))}

    items: list[CartItemView] = []
    for id_str, qty in quantities.items():
        menu_item = rows.get(int(id_str))
        if menu_item is None:
            continue  # item was deleted; drop it from the view
        line_total = menu_item.price * qty
        items.append(
            CartItemView(
                menu_item_id=menu_item.id,
                name=menu_item.name,
                unit_price=menu_item.price,
                quantity=qty,
                line_total=line_total,
            )
        )

    items.sort(key=lambda x: x.menu_item_id)
    subtotal = sum((i.line_total for i in items), Decimal("0"))
    return CartView(
        restaurant_id=data.get("restaurant_id"),
        items=items,
        subtotal=subtotal,
        price_hash=_price_hash(items),
    )


async def get_cart(redis: Redis, session: AsyncSession, user_id: int) -> CartView:
    return await _build_view(session, await _load(redis, user_id))


async def add_item(
    redis: Redis, session: AsyncSession, user_id: int, menu_item_id: int, quantity: int = 1
) -> CartView:
    menu_item = await session.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise NotFoundException("Menu item", str(menu_item_id))

    data = await _load(redis, user_id)
    if data["items"] and data.get("restaurant_id") not in (None, menu_item.restaurant_id):
        raise ConflictException(
            "Your cart contains items from another restaurant. Clear it before ordering elsewhere."
        )

    data["restaurant_id"] = menu_item.restaurant_id
    key = str(menu_item_id)
    data["items"][key] = data["items"].get(key, 0) + quantity
    await _save(redis, user_id, data)
    return await _build_view(session, data)


async def update_item(
    redis: Redis, session: AsyncSession, user_id: int, menu_item_id: int, quantity: int
) -> CartView:
    data = await _load(redis, user_id)
    key = str(menu_item_id)
    if key not in data["items"]:
        raise NotFoundException("Cart item", str(menu_item_id))

    if quantity <= 0:
        del data["items"][key]
    else:
        data["items"][key] = quantity

    if not data["items"]:
        data["restaurant_id"] = None
    await _save(redis, user_id, data)
    return await _build_view(session, data)


async def remove_item(redis: Redis, session: AsyncSession, user_id: int, menu_item_id: int) -> CartView:
    return await update_item(redis, session, user_id, menu_item_id, 0)


async def clear_cart(redis: Redis, user_id: int) -> None:
    await redis.delete(_key(user_id))

"""The cart: Redis-backed, and now self-contained.

The monolith stored only ``{menu_item_id: quantity}`` and rebuilt the view by
reading the menu table on every request, so a cart always showed live prices.
There is no menu table here, and doing that over HTTP would mean one call to the
restaurants service every time anyone glances at their cart — on a page that
polls.

So the cart stores the name and price too, captured **once** when the item is
added. Reading a cart is then entirely local, and the price the customer sees is
the price they were shown when they added it, which is the honest thing to show
anyway.

Staleness is handled where it matters rather than everywhere: ``price_hash``
still fingerprints what they saw, and checkout revalidates every line against
the restaurants service before an order exists. A price that moved in between
produces PRICE_MISMATCH_REFRESH — the same code the frontend already handles —
instead of a silently wrong total.
"""

import hashlib
import json
from decimal import Decimal

from redis.asyncio import Redis

from app.cart_schemas import CartItemView, CartView
from app.clients import restaurants
from shared.errors import ConflictException, NotFoundException

_CART_KEY = "cart:{user_id}"
_TTL_SECONDS = 60 * 60 * 24 * 7


def _key(user_id: int) -> str:
    return _CART_KEY.format(user_id=user_id)


async def _load(redis: Redis, user_id: int) -> dict:
    raw = await redis.get(_key(user_id))
    if not raw:
        return {"restaurant_id": None, "items": {}}
    return json.loads(raw)


async def _save(redis: Redis, user_id: int, data: dict) -> None:
    await redis.set(_key(user_id), json.dumps(data, default=str), ex=_TTL_SECONDS)


def _price_hash(items: list[CartItemView]) -> str:
    payload = ";".join(
        f"{i.menu_item_id}:{i.unit_price}"
        for i in sorted(items, key=lambda x: x.menu_item_id)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _view(data: dict) -> CartView:
    """Build the cart view from what is stored. No I/O at all."""
    stored: dict[str, dict] = data.get("items", {})
    if not stored:
        return CartView()

    items: list[CartItemView] = []
    for id_str, line in stored.items():
        unit_price = Decimal(str(line["unit_price"]))
        quantity = int(line["quantity"])
        items.append(
            CartItemView(
                menu_item_id=int(id_str),
                name=line["name"],
                unit_price=unit_price,
                quantity=quantity,
                line_total=unit_price * quantity,
            )
        )

    items.sort(key=lambda x: x.menu_item_id)
    return CartView(
        restaurant_id=data.get("restaurant_id"),
        items=items,
        subtotal=sum((i.line_total for i in items), Decimal("0")),
        price_hash=_price_hash(items),
    )


async def get_cart(redis: Redis, user_id: int) -> CartView:
    return _view(await _load(redis, user_id))


async def add_item(
    redis: Redis, user_id: int, menu_item_id: int, quantity: int, auth_header: str
) -> CartView:
    """Add an item, capturing its name and price as they are right now.

    The one call to the restaurants service in the cart's whole life. If it is
    unavailable this raises 503 — the customer cannot add an item we cannot
    price, and guessing would be worse than saying so.
    """
    rows = await restaurants().get_json(
        "/restaurants/items/lookup",
        params={"ids": str(menu_item_id)},
        auth_header=auth_header,
    )
    # Reached only when the lookup itself succeeded, so an empty result means
    # the menu item is genuinely not there — not that we failed to ask.
    if not rows:
        raise NotFoundException("Menu item", str(menu_item_id))
    item = rows[0]
    if not item.get("is_available", True):
        raise ConflictException("This item is not available right now.")

    data = await _load(redis, user_id)
    # One restaurant per cart: a delivery comes from one kitchen, and mixing two
    # produces an order nobody can fulfil.
    if data.get("restaurant_id") not in (None, item["restaurant_id"]):
        raise ConflictException(
            "Your cart has items from another restaurant. Clear it to order from this one."
        )
    data["restaurant_id"] = item["restaurant_id"]

    line = data["items"].get(str(menu_item_id))
    new_quantity = (int(line["quantity"]) if line else 0) + quantity
    data["items"][str(menu_item_id)] = {
        "name": item["name"],
        # Refreshed on every add, so a re-add picks up a price change rather
        # than pinning the first one the customer ever saw.
        "unit_price": str(item["price"]),
        "quantity": new_quantity,
    }
    await _save(redis, user_id, data)
    return _view(data)


async def update_item(
    redis: Redis, user_id: int, menu_item_id: int, quantity: int
) -> CartView:
    """Set a line's quantity, or remove it at zero. Entirely local."""
    data = await _load(redis, user_id)
    key = str(menu_item_id)
    if key not in data.get("items", {}):
        raise NotFoundException("Cart item", key)

    if quantity <= 0:
        del data["items"][key]
    else:
        data["items"][key]["quantity"] = quantity

    if not data["items"]:
        data["restaurant_id"] = None
    await _save(redis, user_id, data)
    return _view(data)


async def remove_item(redis: Redis, user_id: int, menu_item_id: int) -> CartView:
    return await update_item(redis, user_id, menu_item_id, 0)


async def clear_cart(redis: Redis, user_id: int) -> None:
    await redis.delete(_key(user_id))

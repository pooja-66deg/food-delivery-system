"""Stock movement for menu items.

Kept in one module so neither the cart nor the orders domain grows inventory
logic of its own. ``stock_quantity IS NULL`` means the item is not tracked, and
untracked items are skipped in every direction — so tracking can be switched on
or off at any time without corrupting a count.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.restaurants.models import MenuItem


def shortfall(item: MenuItem, quantity: int) -> bool:
    """True if ``quantity`` cannot be met from what is left."""
    return item.stock_quantity is not None and item.stock_quantity < quantity


async def apply_order(session: AsyncSession, order_items) -> None:
    """Decrement stock for the lines of an order being placed.

    Called inside the caller's transaction; it does not commit.
    """
    await _move(session, order_items, sign=-1)


async def restore_order(session: AsyncSession, order_items) -> None:
    """Put stock back for the lines of a cancelled or rejected order."""
    await _move(session, order_items, sign=1)


async def _move(session: AsyncSession, order_items, sign: int) -> None:
    wanted = {line.menu_item_id: 0 for line in order_items}
    for line in order_items:
        wanted[line.menu_item_id] += line.quantity
    if not wanted:
        return

    # An order line can outlive the menu item it points at (no foreign key), so
    # anything missing is simply skipped.
    rows = await session.scalars(select(MenuItem).where(MenuItem.id.in_(wanted)))
    for item in rows:
        if item.stock_quantity is None:
            continue
        item.stock_quantity = max(0, item.stock_quantity + sign * wanted[item.id])

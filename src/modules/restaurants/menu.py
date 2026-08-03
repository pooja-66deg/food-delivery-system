"""Business logic for menu categories and items.

All mutating operations verify the caller owns the restaurant (via
``service.owned_restaurant``). Reads (``list_categories``, ``get_menu``) are
public.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, NotFoundException
from src.modules.restaurants import service
from src.modules.restaurants.models import MenuCategory, MenuItem
from src.modules.restaurants.schemas import (
    CategoryCreate,
    CategoryUpdate,
    MenuCategoryWithItems,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from src.modules.users.models import User


async def add_category(
    session: AsyncSession, user: User, restaurant_id: int, data: CategoryCreate
) -> MenuCategory:
    await service.owned_restaurant(session, user, restaurant_id)
    category = MenuCategory(restaurant_id=restaurant_id, **data.model_dump())
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def list_categories(session: AsyncSession, restaurant_id: int) -> list[MenuCategory]:
    stmt = (
        select(MenuCategory)
        .where(MenuCategory.restaurant_id == restaurant_id)
        .order_by(MenuCategory.sort_order, MenuCategory.id)
    )
    return list(await session.scalars(stmt))


async def update_category(
    session: AsyncSession, user: User, restaurant_id: int, category_id: int, data: CategoryUpdate
) -> MenuCategory:
    """Rename or reorder a category. Omitted fields are left alone."""
    await service.owned_restaurant(session, user, restaurant_id)
    category = await _category_in_restaurant(session, restaurant_id, category_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(category, field, value)
    await session.commit()
    await session.refresh(category)
    return category


async def delete_category(
    session: AsyncSession, user: User, restaurant_id: int, category_id: int
) -> None:
    """Delete an empty category.

    A category holding items is refused rather than cascaded — one stray click
    must not erase a whole menu section. The owner moves or deletes the items
    first.
    """
    await service.owned_restaurant(session, user, restaurant_id)
    category = await _category_in_restaurant(session, restaurant_id, category_id)

    held = await session.scalar(
        select(func.count()).select_from(MenuItem).where(MenuItem.category_id == category_id)
    )
    if held:
        raise ConflictException(
            f"'{category.name}' still has {held} item(s). Move or delete them first."
        )

    await session.delete(category)
    await session.commit()


async def _category_in_restaurant(session: AsyncSession, restaurant_id: int, category_id: int) -> MenuCategory:
    category = await session.get(MenuCategory, category_id)
    if category is None or category.restaurant_id != restaurant_id:
        raise NotFoundException("Category", str(category_id))
    return category


async def _item_in_restaurant(session: AsyncSession, restaurant_id: int, item_id: int) -> MenuItem:
    item = await session.get(MenuItem, item_id)
    if item is None or item.restaurant_id != restaurant_id:
        raise NotFoundException("Menu item", str(item_id))
    return item


async def add_item(
    session: AsyncSession, user: User, restaurant_id: int, data: MenuItemCreate
) -> MenuItem:
    await service.owned_restaurant(session, user, restaurant_id)
    await _category_in_restaurant(session, restaurant_id, data.category_id)
    item = MenuItem(restaurant_id=restaurant_id, **data.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_item(
    session: AsyncSession, user: User, restaurant_id: int, item_id: int, data: MenuItemUpdate
) -> MenuItem:
    await service.owned_restaurant(session, user, restaurant_id)
    item = await _item_in_restaurant(session, restaurant_id, item_id)
    updates = data.model_dump(exclude_unset=True)
    if "category_id" in updates:
        await _category_in_restaurant(session, restaurant_id, updates["category_id"])
    for field, value in updates.items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, user: User, restaurant_id: int, item_id: int) -> None:
    await service.owned_restaurant(session, user, restaurant_id)
    item = await _item_in_restaurant(session, restaurant_id, item_id)
    await session.delete(item)
    await session.commit()


async def get_menu(
    session: AsyncSession, restaurant_id: int, available_only: bool = False
) -> list[MenuCategoryWithItems]:
    """Return the menu as categories (ordered) each carrying their items."""
    categories = await list_categories(session, restaurant_id)

    item_stmt = select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
    if available_only:
        item_stmt = item_stmt.where(MenuItem.is_available.is_(True))
    item_stmt = item_stmt.order_by(MenuItem.id)
    items = list(await session.scalars(item_stmt))

    by_category: dict[int, list[MenuItem]] = {}
    for item in items:
        by_category.setdefault(item.category_id, []).append(item)

    return [
        MenuCategoryWithItems(
            id=category.id,
            name=category.name,
            sort_order=category.sort_order,
            items=[MenuItemResponse.model_validate(i) for i in by_category.get(category.id, [])],
        )
        for category in categories
    ]

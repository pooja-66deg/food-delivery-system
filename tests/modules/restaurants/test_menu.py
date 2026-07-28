"""Tests for menu category/item management."""

from decimal import Decimal

import pytest

from src.core.exceptions import ForbiddenException, NotFoundException
from src.modules.restaurants import menu, service
from src.modules.restaurants.schemas import (
    CategoryCreate,
    MenuItemCreate,
    MenuItemUpdate,
    RestaurantCreate,
)
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister


async def _owner(db_session, email="owner@example.com", phone="+15557770001"):
    return await users_service.register_user(
        db_session,
        UserRegister(
            email=email, phone=phone, first_name="Ola", last_name="Owner",
            password="supersecret1", role="restaurant",
        ),
    )


async def _owner_and_restaurant(db_session):
    owner = await _owner(db_session)
    restaurant = await service.create_restaurant(
        db_session,
        owner,
        RestaurantCreate(name="Pizza Palace", city="Metropolis", address_line="1 Main St", phone="+15550000000"),
    )
    return owner, restaurant


@pytest.mark.asyncio
async def test_add_and_list_categories(db_session):
    owner, r = await _owner_and_restaurant(db_session)

    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Starters", sort_order=1))
    assert cat.id is not None

    cats = await menu.list_categories(db_session, r.id)
    assert [c.name for c in cats] == ["Starters"]


@pytest.mark.asyncio
async def test_add_item_to_category(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))

    item = await menu.add_item(
        db_session, owner, r.id,
        MenuItemCreate(category_id=cat.id, name="Margherita", price=Decimal("9.50")),
    )

    assert item.id is not None
    assert item.restaurant_id == r.id
    assert item.price == Decimal("9.50")
    assert item.is_available is True


@pytest.mark.asyncio
async def test_add_item_rejects_category_from_another_restaurant(db_session):
    owner, r1 = await _owner_and_restaurant(db_session)
    r2 = await service.create_restaurant(
        db_session, owner,
        RestaurantCreate(name="Other", city="Metropolis", address_line="2 St", phone="+15550000001"),
    )
    cat_r2 = await menu.add_category(db_session, owner, r2.id, CategoryCreate(name="X"))

    with pytest.raises(NotFoundException):
        await menu.add_item(
            db_session, owner, r1.id,
            MenuItemCreate(category_id=cat_r2.id, name="Sneaky", price=Decimal("1.00")),
        )


@pytest.mark.asyncio
async def test_update_item_price_and_availability(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))
    item = await menu.add_item(
        db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Burger", price=Decimal("8.00"))
    )

    updated = await menu.update_item(
        db_session, owner, r.id, item.id, MenuItemUpdate(price=Decimal("8.50"), is_available=False)
    )

    assert updated.price == Decimal("8.50")
    assert updated.is_available is False


@pytest.mark.asyncio
async def test_delete_item(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))
    item = await menu.add_item(
        db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Fries", price=Decimal("3.00"))
    )

    await menu.delete_item(db_session, owner, r.id, item.id)

    menu_view = await menu.get_menu(db_session, r.id)
    assert menu_view[0].items == []


@pytest.mark.asyncio
async def test_menu_management_requires_ownership(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    intruder = await _owner(db_session, email="intruder@example.com", phone="+15557770002")

    with pytest.raises(ForbiddenException):
        await menu.add_category(db_session, intruder, r.id, CategoryCreate(name="Nope"))


@pytest.mark.asyncio
async def test_get_menu_groups_items_by_category_ordered(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    mains = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains", sort_order=2))
    starters = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Starters", sort_order=1))
    await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=mains.id, name="Burger", price=Decimal("8")))
    await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=starters.id, name="Soup", price=Decimal("4")))

    view = await menu.get_menu(db_session, r.id)

    assert [c.name for c in view] == ["Starters", "Mains"]  # by sort_order
    assert view[1].items[0].name == "Burger"


@pytest.mark.asyncio
async def test_get_menu_available_only_filters_unavailable(db_session):
    owner, r = await _owner_and_restaurant(db_session)
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))
    await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Available", price=Decimal("5")))
    hidden = await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Hidden", price=Decimal("5")))
    await menu.update_item(db_session, owner, r.id, hidden.id, MenuItemUpdate(is_available=False))

    view = await menu.get_menu(db_session, r.id, available_only=True)

    assert [i.name for i in view[0].items] == ["Available"]

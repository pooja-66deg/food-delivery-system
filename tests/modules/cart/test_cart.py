"""Tests for the Redis-backed cart service."""

from decimal import Decimal

import pytest

from src.core.exceptions import ConflictException, NotFoundException
from src.modules.cart import service as cart
from src.modules.restaurants import menu, service as rest_service
from src.modules.restaurants.schemas import CategoryCreate, MenuItemCreate, RestaurantCreate
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister


async def _make_user(db_session, email, phone, role="customer"):
    return await users_service.register_user(
        db_session,
        UserRegister(email=email, phone=phone, first_name="T", last_name="U", password="supersecret1", role=role),
    )


async def _setup(db_session):
    owner = await _make_user(db_session, "owner@example.com", "+15557000001", role="restaurant")
    customer = await _make_user(db_session, "cust@example.com", "+15557000002")
    r = await rest_service.create_restaurant(
        db_session, owner,
        RestaurantCreate(name="Pizza", city="Metropolis", address_line="1 St", phone="+15550000000"),
    )
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))
    item1 = await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Pizza", price=Decimal("10.00")))
    item2 = await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Cola", price=Decimal("2.50")))
    return customer, r, item1, item2


@pytest.mark.asyncio
async def test_add_item_creates_cart_with_subtotal(fake_redis, db_session):
    customer, r, item1, _ = await _setup(db_session)

    view = await cart.add_item(fake_redis, db_session, customer.id, item1.id, 2)

    assert view.restaurant_id == r.id
    assert len(view.items) == 1
    assert view.items[0].quantity == 2
    assert view.subtotal == Decimal("20.00")
    assert view.price_hash  # a stable signature is produced


@pytest.mark.asyncio
async def test_add_same_item_increments_quantity(fake_redis, db_session):
    customer, _, item1, _ = await _setup(db_session)

    await cart.add_item(fake_redis, db_session, customer.id, item1.id, 1)
    view = await cart.add_item(fake_redis, db_session, customer.id, item1.id, 2)

    assert view.items[0].quantity == 3


@pytest.mark.asyncio
async def test_add_item_from_another_restaurant_rejected(fake_redis, db_session):
    customer, _, item1, _ = await _setup(db_session)
    # a second restaurant with its own item
    owner2 = await _make_user(db_session, "owner2@example.com", "+15557000003", role="restaurant")
    r2 = await rest_service.create_restaurant(
        db_session, owner2, RestaurantCreate(name="Sushi", city="Metropolis", address_line="2 St", phone="+15550000009"),
    )
    cat2 = await menu.add_category(db_session, owner2, r2.id, CategoryCreate(name="Rolls"))
    item_r2 = await menu.add_item(db_session, owner2, r2.id, MenuItemCreate(category_id=cat2.id, name="Maki", price=Decimal("7")))

    await cart.add_item(fake_redis, db_session, customer.id, item1.id, 1)
    with pytest.raises(ConflictException):
        await cart.add_item(fake_redis, db_session, customer.id, item_r2.id, 1)


@pytest.mark.asyncio
async def test_update_quantity_to_zero_removes_item(fake_redis, db_session):
    customer, _, item1, item2 = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item1.id, 1)
    await cart.add_item(fake_redis, db_session, customer.id, item2.id, 1)

    view = await cart.update_item(fake_redis, db_session, customer.id, item1.id, 0)

    assert [i.menu_item_id for i in view.items] == [item2.id]


@pytest.mark.asyncio
async def test_clear_empties_cart(fake_redis, db_session):
    customer, _, item1, _ = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item1.id, 1)

    await cart.clear_cart(fake_redis, customer.id)
    view = await cart.get_cart(fake_redis, db_session, customer.id)

    assert view.items == []
    assert view.restaurant_id is None


@pytest.mark.asyncio
async def test_add_unknown_item_raises(fake_redis, db_session):
    customer, _, _, _ = await _setup(db_session)
    with pytest.raises(NotFoundException):
        await cart.add_item(fake_redis, db_session, customer.id, 99999, 1)

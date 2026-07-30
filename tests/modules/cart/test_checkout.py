"""Tests for the checkout validation pipeline (blueprint §15)."""

from decimal import Decimal

import pytest

from src.modules.cart import checkout, service as cart
from src.modules.cart.checkout import CheckoutError
from src.modules.cart.schemas import CheckoutRequest
from src.modules.restaurants import menu, service as rest_service
from src.modules.restaurants.schemas import (
    CategoryCreate,
    MenuItemCreate,
    RestaurantCreate,
    RestaurantUpdate,
)
from src.modules.users import profile, service as users_service
from src.modules.users.schemas import AddressCreate, UserRegister


async def _make_user(db_session, email, phone, role="customer"):
    return await users_service.register_user(
        db_session,
        UserRegister(email=email, phone=phone, first_name="T", last_name="U", password="supersecret1", role=role),
    )


async def _setup(db_session, *, city="Metropolis", min_order="5.00", is_open=True):
    owner = await _make_user(db_session, "owner@example.com", "+15558000001", role="restaurant")
    customer = await _make_user(db_session, "cust@example.com", "+15558000002")
    r = await rest_service.create_restaurant(
        db_session, owner,
        RestaurantCreate(name="Pizza", city=city, address_line="1 St", phone="+15550000000", min_order_amount=Decimal(min_order)),
    )
    await rest_service.update_restaurant(db_session, r.id, owner, RestaurantUpdate(is_open=is_open))
    cat = await menu.add_category(db_session, owner, r.id, CategoryCreate(name="Mains"))
    item = await menu.add_item(db_session, owner, r.id, MenuItemCreate(category_id=cat.id, name="Pizza", price=Decimal("10.00")))
    address = await profile.add_address(
        db_session, customer, AddressCreate(label="home", line1="1 Main St", city="Metropolis", postal_code="12345")
    )
    return owner, customer, r, item, address


async def _checkout(fake_redis, db_session, customer, address, *, price_hash=None):
    view = await cart.get_cart(fake_redis, db_session, customer.id)
    req = CheckoutRequest(address_id=address.id, price_hash=price_hash or view.price_hash)
    return await checkout.validate_checkout(fake_redis, db_session, customer, req)


@pytest.mark.asyncio
async def test_checkout_success_returns_validated_order(fake_redis, db_session):
    owner, customer, r, item, address = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 2)  # subtotal 20 >= 5

    order = await _checkout(fake_redis, db_session, customer, address)

    assert order.restaurant_id == r.id
    assert order.address_id == address.id
    assert order.subtotal == Decimal("20.00")
    assert order.items[0].menu_item_id == item.id
    assert order.items[0].quantity == 2


@pytest.mark.asyncio
async def test_checkout_empty_cart_rejected(fake_redis, db_session):
    _, customer, _, _, address = await _setup(db_session)
    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address, price_hash="anything")
    assert exc.value.code == "EMPTY_CART"


@pytest.mark.asyncio
async def test_checkout_rejected_when_restaurant_closed(fake_redis, db_session):
    _, customer, _, item, address = await _setup(db_session, is_open=False)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address)
    assert exc.value.code == "RESTAURANT_CLOSED"


@pytest.mark.asyncio
async def test_checkout_rejected_when_item_out_of_stock(fake_redis, db_session):
    owner, customer, r, item, address = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    from src.modules.restaurants.schemas import MenuItemUpdate
    await menu.update_item(db_session, owner, r.id, item.id, MenuItemUpdate(is_available=False))

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address)
    assert exc.value.code == "ITEM_OUT_OF_STOCK"


@pytest.mark.asyncio
async def test_checkout_rejected_on_price_mismatch(fake_redis, db_session):
    _, customer, _, item, address = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address, price_hash="stale-hash")
    assert exc.value.code == "PRICE_MISMATCH_REFRESH"


@pytest.mark.asyncio
async def test_checkout_rejected_when_address_out_of_zone(fake_redis, db_session):
    _, customer, _, item, _ = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    far = await profile.add_address(
        db_session, customer, AddressCreate(label="away", line1="9 Far Rd", city="Gotham", postal_code="99999")
    )

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, far)
    assert exc.value.code == "ADDRESS_OUT_OF_ZONE"


@pytest.mark.asyncio
async def test_checkout_zone_match_is_case_insensitive(fake_redis, db_session):
    # Restaurant city "Metropolis"; address " metropolis " should still be in zone.
    owner, customer, r, item, _ = await _setup(db_session)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    addr = await profile.add_address(
        db_session, customer,
        AddressCreate(label="home2", line1="2 Main St", city=" metropolis ", postal_code="12345"),
    )
    order = await _checkout(fake_redis, db_session, customer, addr)  # no CheckoutError
    assert order.address_id == addr.id


@pytest.mark.asyncio
async def test_checkout_rejected_when_below_min_order(fake_redis, db_session):
    owner, customer, r, item, address = await _setup(db_session, min_order="25.00")
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)  # 10 < 25

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address)
    assert exc.value.code == "MIN_ORDER_NOT_MET"

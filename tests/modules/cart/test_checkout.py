"""Tests for the checkout validation pipeline (blueprint §15)."""

from decimal import Decimal

import pytest

from src.modules.cart import checkout, service as cart
from src.modules.cart.checkout import CheckoutError
from src.modules.cart.schemas import CheckoutRequest
from src.modules.delivery.providers import Coordinate
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


async def _setup(
    db_session, *, city="Metropolis", min_order="5.00", is_open=True, coords=None, radius_km=None
):
    owner = await _make_user(db_session, "owner@example.com", "+15558000001", role="restaurant")
    customer = await _make_user(db_session, "cust@example.com", "+15558000002")
    latitude, longitude = coords if coords else (None, None)
    r = await rest_service.create_restaurant(
        db_session, owner,
        RestaurantCreate(name="Pizza", city=city, address_line="1 St", phone="+15550000000",
                         min_order_amount=Decimal(min_order), latitude=latitude,
                         longitude=longitude, delivery_radius_km=radius_km),
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


class _FixedGeocoder:
    """Geocodes every address to one point, so a test can place an address
    precisely instead of depending on a live geocoder."""

    def __init__(self, latitude: float, longitude: float):
        self.point = Coordinate(latitude=latitude, longitude=longitude)

    async def geocode(self, line1: str, city: str, postal_code: str) -> Coordinate:
        return self.point


# Restaurant origin, a point ~4.5 km from it, and one ~44 km from it.
_ORIGIN = (21.1702, 72.8311)
_NEAR = (21.2000, 72.8400)
_FAR = (21.5650, 72.8311)


async def _placed_address(db_session, customer, point, *, city="Metropolis", label="geo"):
    return await profile.add_address(
        db_session, customer,
        AddressCreate(label=label, line1="1 Geo St", city=city, postal_code="12345"),
        geocoder=_FixedGeocoder(*point),
    )


@pytest.mark.asyncio
async def test_checkout_rejected_when_geocoded_address_is_beyond_the_radius(
    fake_redis, db_session
):
    """Same city, 44 km away — the case the old city match let through."""
    owner, customer, r, item, _ = await _setup(db_session, coords=_ORIGIN, radius_km=10)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    far = await _placed_address(db_session, customer, _FAR)

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, far)

    assert exc.value.code == "ADDRESS_OUT_OF_ZONE"
    # The message names the numbers so the customer can judge another address.
    assert "km" in exc.value.message


@pytest.mark.asyncio
async def test_checkout_accepts_a_nearby_address_in_a_different_city(fake_redis, db_session):
    """The other half of the change: a neighbouring town within range works."""
    owner, customer, r, item, _ = await _setup(db_session, coords=_ORIGIN, radius_km=10)
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    near = await _placed_address(db_session, customer, _NEAR, city="Gotham")

    order = await _checkout(fake_redis, db_session, customer, near)  # no CheckoutError

    assert order.address_id == near.id


@pytest.mark.asyncio
async def test_checkout_still_uses_city_when_the_restaurant_is_ungeocoded(
    fake_redis, db_session
):
    """A restaurant with no coordinates cannot measure anything, so the city
    match stays in force even for a precisely-placed address."""
    owner, customer, r, item, _ = await _setup(db_session)  # no coords
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)
    far_but_same_city = await _placed_address(db_session, customer, _FAR)

    order = await _checkout(fake_redis, db_session, customer, far_but_same_city)

    assert order.address_id == far_but_same_city.id


@pytest.mark.asyncio
async def test_checkout_rejected_when_below_min_order(fake_redis, db_session):
    owner, customer, r, item, address = await _setup(db_session, min_order="25.00")
    await cart.add_item(fake_redis, db_session, customer.id, item.id, 1)  # 10 < 25

    with pytest.raises(CheckoutError) as exc:
        await _checkout(fake_redis, db_session, customer, address)
    assert exc.value.code == "MIN_ORDER_NOT_MET"

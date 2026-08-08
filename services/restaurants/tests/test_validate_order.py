"""The one synchronous call in the whole platform.

Checkout depends on this endpoint answering correctly, so these tests are the
closest thing the split has to a load-bearing contract. Two properties matter
beyond the individual rules:

- a rejection is a 200 with ``ok: false``, not an HTTP error, because the caller
  has to tell "your cart is invalid" apart from "this service is unreachable";
- stock is reserved in the same transaction as the checks, or two customers can
  both be told they got the last portion.
"""

from decimal import Decimal

import pytest
from app.models import MenuCategory, MenuItem, Restaurant


@pytest.fixture
async def kitchen(session):
    """An open restaurant with one tracked, available dish."""
    restaurant = Restaurant(
        owner_id=7, name="Test Kitchen", city="Metropolis", address_line="1 Main St",
        phone="+919876543210", is_open=True, min_order_amount=Decimal("1.00"),
    )
    session.add(restaurant)
    await session.flush()
    category = MenuCategory(restaurant_id=restaurant.id, name="Mains", sort_order=0)
    session.add(category)
    await session.flush()
    item = MenuItem(
        restaurant_id=restaurant.id, category_id=category.id, name="Pizza",
        price=Decimal("12.00"), is_available=True, stock_quantity=5, is_vegetarian=False,
    )
    session.add(item)
    await session.commit()
    return {"restaurant": restaurant, "item": item}


def _body(item_id, quantity=1, unit_price="12.00", city="Metropolis", reserve=True):
    return {
        "items": [{"menu_item_id": item_id, "quantity": quantity, "unit_price": unit_price}],
        "address": {"city": city, "latitude": None, "longitude": None},
        "reserve": reserve,
    }


async def test_a_valid_order_passes_and_reserves(client, auth, session, kitchen):
    item = kitchen["item"]
    r = await client.post(
        f"/restaurants/{item.restaurant_id}/validate-order",
        json=_body(item.id, quantity=2), headers=auth(role="customer"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert Decimal(body["subtotal"]) == Decimal("24.00")

    await session.refresh(item)
    assert item.stock_quantity == 3, "stock was not reserved by the call that approved it"


async def test_a_rejection_is_a_200_not_an_error(client, auth, session, kitchen):
    """The distinction the caller depends on.

    A 4xx here would be indistinguishable from the restaurants service being
    broken, and checkout would retry something that will never succeed.
    """
    restaurant = kitchen["restaurant"]
    restaurant.is_open = False
    # Committed, because the app serves the request on its own session.
    await session.commit()
    r = await client.post(
        f"/restaurants/{restaurant.id}/validate-order",
        json=_body(kitchen["item"].id), headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["code"] == "RESTAURANT_CLOSED"


async def test_a_closed_kitchen_reserves_nothing(client, auth, session, kitchen):
    kitchen["restaurant"].is_open = False
    await session.commit()
    await client.post(
        f"/restaurants/{kitchen['restaurant'].id}/validate-order",
        json=_body(kitchen["item"].id), headers=auth(),
    )
    await session.refresh(kitchen["item"])
    assert kitchen["item"].stock_quantity == 5


async def test_a_price_that_moved_is_refused(client, auth, session, kitchen):
    """The customer agreed to a number. Charging a different one is not an option."""
    item = kitchen["item"]
    r = await client.post(
        f"/restaurants/{item.restaurant_id}/validate-order",
        json=_body(item.id, unit_price="9.00"), headers=auth(),
    )
    assert r.json()["code"] == "PRICE_MISMATCH_REFRESH"
    await session.refresh(item)
    assert item.stock_quantity == 5


async def test_more_than_is_left_is_refused(client, auth, kitchen):
    item = kitchen["item"]
    r = await client.post(
        f"/restaurants/{item.restaurant_id}/validate-order",
        json=_body(item.id, quantity=99), headers=auth(),
    )
    assert r.json()["code"] == "ITEM_OUT_OF_STOCK"


async def test_an_unavailable_dish_is_refused(client, auth, session, kitchen):
    kitchen["item"].is_available = False
    await session.commit()
    r = await client.post(
        f"/restaurants/{kitchen['restaurant'].id}/validate-order",
        json=_body(kitchen["item"].id), headers=auth(),
    )
    assert r.json()["code"] == "ITEM_OUT_OF_STOCK"


async def test_another_city_is_out_of_zone(client, auth, kitchen):
    """With no coordinates on either end the check falls back to a city match —
    the pre-radius rule, kept so an ungeocoded address still orders locally."""
    r = await client.post(
        f"/restaurants/{kitchen['restaurant'].id}/validate-order",
        json=_body(kitchen["item"].id, city="Gotham"), headers=auth(),
    )
    assert r.json()["code"] == "ADDRESS_OUT_OF_ZONE"


async def test_below_the_minimum_is_refused(client, auth, session, kitchen):
    kitchen["restaurant"].min_order_amount = Decimal("50.00")
    await session.commit()
    r = await client.post(
        f"/restaurants/{kitchen['restaurant'].id}/validate-order",
        json=_body(kitchen["item"].id), headers=auth(),
    )
    assert r.json()["code"] == "MIN_ORDER_NOT_MET"


async def test_reserve_false_checks_without_taking(client, auth, session, kitchen):
    item = kitchen["item"]
    r = await client.post(
        f"/restaurants/{item.restaurant_id}/validate-order",
        json=_body(item.id, reserve=False), headers=auth(),
    )
    assert r.json()["ok"] is True
    await session.refresh(item)
    assert item.stock_quantity == 5


async def test_an_item_from_another_restaurant_is_not_accepted(client, auth, session, kitchen):
    """Scoped to the restaurant in the path, so a crafted cart cannot pull a
    cheap dish from one kitchen into an order at another."""
    other = Restaurant(
        owner_id=8, name="Elsewhere", city="Metropolis", address_line="2 Main St",
        phone="+919876543211", is_open=True, min_order_amount=Decimal("0"),
    )
    session.add(other)
    await session.commit()

    r = await client.post(
        f"/restaurants/{other.id}/validate-order",
        json=_body(kitchen["item"].id), headers=auth(),
    )
    assert r.json()["code"] == "ITEM_OUT_OF_STOCK"


async def test_an_unknown_restaurant_is_a_404(client, auth):
    r = await client.post(
        "/restaurants/9999/validate-order", json=_body(1), headers=auth()
    )
    assert r.status_code == 404


async def test_release_puts_stock_back(client, auth, session, kitchen):
    item = kitchen["item"]
    await client.post(
        f"/restaurants/{item.restaurant_id}/validate-order",
        json=_body(item.id, quantity=2), headers=auth(),
    )
    await session.refresh(item)
    assert item.stock_quantity == 3

    r = await client.post(
        f"/restaurants/{item.restaurant_id}/release-stock",
        json={"items": [{"menu_item_id": item.id, "quantity": 2, "unit_price": "12.00"}]},
        headers=auth(),
    )
    assert r.status_code == 204
    await session.refresh(item)
    assert item.stock_quantity == 5

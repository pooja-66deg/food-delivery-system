"""Checkout: the cart, the one synchronous call, and what happens when it fails.

The restaurants service is stubbed here rather than run, because what these
tests are about is how *this* service behaves given each answer it might get —
including no answer at all, which is the case the monolith never had to have an
opinion about.
"""

import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.models import AddressSnapshot, Order, OutboxEvent


@pytest.fixture(autouse=True)
def restaurants_stub(monkeypatch):
    """Stand in for the restaurants service.

    Returns a handle whose ``responses`` list is consumed in order, so a test can
    say "the lookup succeeds, then validate-order refuses" without writing a
    router.
    """
    from app import clients
    from shared.http_client import ServiceClient

    state = {"responses": [], "requests": []}

    def _handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if not state["responses"]:
            raise AssertionError(f"unexpected call to {request.url.path}")
        return state["responses"].pop(0)

    stub = ServiceClient("http://restaurants", name="restaurants-service")
    stub._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler), base_url="http://restaurants"
    )

    # Patched in every module that imported the name, not just in clients.py:
    # `from app.clients import restaurants` binds at import time, so replacing
    # the attribute on clients alone leaves cart and checkout still holding the
    # real one.
    from app import cart, checkout, reorder

    for module in (clients, cart, checkout, reorder):
        monkeypatch.setattr(module, "restaurants", lambda: stub)
    return state


def _item(menu_item_id=1, name="Pizza", price="12.00", stock=5, available=True):
    return {
        "id": menu_item_id, "restaurant_id": 10, "name": name, "price": price,
        "is_available": available, "stock_quantity": stock,
    }


def _validated(subtotal="12.00"):
    return {
        "ok": True, "code": None, "message": None, "restaurant_id": 10,
        "items": [{"menu_item_id": 1, "name": "Pizza", "unit_price": "12.00",
                   "quantity": 1, "line_total": "12.00"}],
        "subtotal": subtotal,
    }


@pytest.fixture
async def address(session):
    snapshot = AddressSnapshot(
        address_id=5, user_id=1, city="Metropolis", latitude=None, longitude=None
    )
    session.add(snapshot)
    await session.commit()
    return snapshot


async def test_adding_to_the_cart_captures_name_and_price(client, auth, restaurants_stub):
    """Captured once, so every later cart read is local.

    The monolith re-read the menu on every cart view; over HTTP that would be a
    call to another service each time somebody glances at their cart.
    """
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    r = await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                          headers=auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"][0]["name"] == "Pizza"
    assert Decimal(body["subtotal"]) == Decimal("12.00")

    # Reading it back makes no further call — the stub would raise if it did.
    again = await client.get("/cart", headers=auth())
    assert again.json()["items"][0]["name"] == "Pizza"


async def test_an_item_that_is_really_missing_is_a_404(client, auth, restaurants_stub):
    """The lookup answered, and the answer was that there is no such dish."""
    restaurants_stub["responses"].append(httpx.Response(200, json=[]))
    r = await client.post("/cart/items", json={"menu_item_id": 404, "quantity": 1},
                          headers=auth())
    assert r.status_code == 404


async def test_a_refused_lookup_is_a_503_not_a_missing_item(client, auth, restaurants_stub):
    """The distinction this endpoint used to lose.

    A 4xx from the lookup — a rejected token, a mistyped path, a gateway that
    routed the call nowhere — was read as an empty result and reported as "that
    dish does not exist". The dish did exist; nobody had asked about it. This
    sent the last debugging session to the menu table for a problem that was in
    the wiring between two services.
    """
    for refusal in (401, 403, 404):
        restaurants_stub["responses"].append(httpx.Response(refusal, json={"detail": "no"}))
        r = await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())
        assert r.status_code == 503, f"{refusal} from the lookup became {r.status_code}"


async def test_the_cart_holds_one_restaurant(client, auth, restaurants_stub):
    """A delivery comes from one kitchen; mixing two produces an order nobody
    can fulfil."""
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1}, headers=auth())

    elsewhere = _item(menu_item_id=2)
    elsewhere["restaurant_id"] = 99
    restaurants_stub["responses"].append(httpx.Response(200, json=[elsewhere]))
    r = await client.post("/cart/items", json={"menu_item_id": 2, "quantity": 1},
                          headers=auth())
    assert r.status_code == 409


async def test_a_successful_checkout_creates_the_order_and_one_event(
    client, auth, session, restaurants_stub, address
):
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    cart = (await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())).json()

    restaurants_stub["responses"].append(httpx.Response(200, json=_validated()))
    r = await client.post("/orders/checkout", json={
        "address_id": 5, "payment_method": "COD", "price_hash": cart["price_hash"],
    }, headers=auth())
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "PAYMENT_SUCCESS"

    orders = list(await session.scalars(select(Order)))
    assert len(orders) == 1
    assert Decimal(orders[0].total) == Decimal("12.00")

    events = [
        json.loads(e.payload)
        for e in await session.scalars(
            select(OutboxEvent).where(OutboxEvent.topic == "order-events")
        )
    ]
    assert len(events) == 1
    assert events[0]["status"] == "PAYMENT_SUCCESS"
    assert events[0]["total"] == "12.00"


async def test_a_restaurants_rejection_is_passed_through_by_code(
    client, auth, restaurants_stub, address
):
    """The frontend keys its messaging off these codes, so they must survive the
    extra hop unchanged."""
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    cart = (await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())).json()

    restaurants_stub["responses"].append(httpx.Response(200, json={
        "ok": False, "code": "RESTAURANT_CLOSED",
        "message": "This restaurant is currently closed.", "items": [], "subtotal": "0",
    }))
    r = await client.post("/orders/checkout", json={
        "address_id": 5, "payment_method": "COD", "price_hash": cart["price_hash"],
    }, headers=auth())
    assert r.status_code == 409
    assert r.json()["details"]["code"] == "RESTAURANT_CLOSED"


async def test_an_unreachable_restaurants_service_is_a_503_not_a_500(
    client, auth, session, restaurants_stub, address
):
    """The distinction that decides whether a client retries.

    A 500 says "we broke"; a 503 says "we could not answer, try again". Checkout
    is exactly where a customer should be told to try again.
    """
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    cart = (await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())).json()

    restaurants_stub["responses"].append(httpx.Response(500, json={"detail": "boom"}))
    r = await client.post("/orders/checkout", json={
        "address_id": 5, "payment_method": "COD", "price_hash": cart["price_hash"],
    }, headers=auth())
    assert r.status_code == 503

    assert list(await session.scalars(select(Order))) == [], "a failed call left an order behind"


async def test_a_stale_price_hash_is_refused_before_any_call(
    client, auth, restaurants_stub, address
):
    """Checked locally first: a stale cart should not cost a network round trip."""
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1}, headers=auth())

    before = len(restaurants_stub["requests"])
    r = await client.post("/orders/checkout", json={
        "address_id": 5, "payment_method": "COD", "price_hash": "stale",
    }, headers=auth())
    assert r.status_code == 409
    assert r.json()["details"]["code"] == "PRICE_MISMATCH_REFRESH"
    assert len(restaurants_stub["requests"]) == before


async def test_an_address_we_have_not_heard_of_is_a_404(client, auth, restaurants_stub):
    """Also the answer when the address exists but its event has not arrived.

    Self-correcting on retry, and far better than accepting an order for
    somewhere we cannot confirm we deliver.
    """
    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    cart = (await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())).json()

    r = await client.post("/orders/checkout", json={
        "address_id": 999, "payment_method": "COD", "price_hash": cart["price_hash"],
    }, headers=auth())
    assert r.status_code == 404


async def test_another_users_address_is_not_usable(client, auth, session, restaurants_stub):
    session.add(AddressSnapshot(address_id=7, user_id=42, city="Metropolis"))
    await session.commit()

    restaurants_stub["responses"].append(httpx.Response(200, json=[_item()]))
    cart = (await client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                              headers=auth())).json()

    r = await client.post("/orders/checkout", json={
        "address_id": 7, "payment_method": "COD", "price_hash": cart["price_hash"],
    }, headers=auth(user_id=1))
    assert r.status_code == 404


async def test_an_empty_cart_cannot_be_checked_out(client, auth, address):
    r = await client.post("/orders/checkout", json={
        "address_id": 5, "payment_method": "COD", "price_hash": "",
    }, headers=auth())
    assert r.status_code == 409
    assert r.json()["details"]["code"] == "EMPTY_CART"

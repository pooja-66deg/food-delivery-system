"""Opening hours: save via the existing PATCH, enforce at validate-order."""

from datetime import datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import MenuCategory, MenuItem, OpeningHour, Restaurant


@pytest.fixture
async def kitchen(session):
    restaurant = Restaurant(
        owner_id=7, name="Hours Kitchen", city="Metropolis", address_line="1 Main St",
        phone="+919876543210", is_open=True, min_order_amount=Decimal("1.00"),
        approval_status="approved",
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


def _body(item_id):
    return {
        "items": [{"menu_item_id": item_id, "quantity": 1, "unit_price": "12.00"}],
        "address": {"city": "Metropolis", "latitude": None, "longitude": None},
        "reserve": True,
    }


async def test_patch_saves_opening_hours(client, auth, session, kitchen):
    rid = kitchen["restaurant"].id
    week = [
        {
            "day_of_week": d,
            "opens_at": "09:00",
            "closes_at": "17:00",
            "is_closed": d >= 5,
        }
        for d in range(7)
    ]
    r = await client.patch(
        f"/restaurants/{rid}",
        json={"opening_hours": week},
        headers=auth(role="restaurant", user_id=7),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["opening_hours"]) == 7
    assert body["opening_hours"][5]["is_closed"] is True
    assert body["opening_hours"][0]["opens_at"] == "09:00"

    rows = list(
        await session.scalars(select(OpeningHour).where(OpeningHour.restaurant_id == rid))
    )
    assert len(rows) == 7


async def test_clearing_hours_restores_manual_only(client, auth, session, kitchen):
    rid = kitchen["restaurant"].id
    session.add(
        OpeningHour(
            restaurant_id=rid, day_of_week=0, opens_at=time(9, 0), closes_at=time(17, 0),
            is_closed=False,
        )
    )
    await session.commit()

    r = await client.patch(
        f"/restaurants/{rid}",
        json={"opening_hours": []},
        headers=auth(role="restaurant", user_id=7),
    )
    assert r.status_code == 200
    assert r.json()["opening_hours"] == []
    assert r.json()["is_accepting_orders"] is True


async def test_validate_rejects_outside_hours(client, auth, session, kitchen, monkeypatch):
    """Schedule tightens the existing RESTAURANT_CLOSED gate; code is unchanged."""
    rid = kitchen["restaurant"].id
    for d in range(7):
        session.add(
            OpeningHour(
                restaurant_id=rid, day_of_week=d,
                opens_at=time(10, 0), closes_at=time(11, 0), is_closed=False,
            )
        )
    await session.commit()

    from app import hours as hours_mod

    monkeypatch.setattr(
        hours_mod, "local_now", lambda now=None: datetime(2026, 8, 19, 15, 0)
    )

    r = await client.post(
        f"/restaurants/{rid}/validate-order",
        json=_body(kitchen["item"].id),
        headers=auth(role="customer"),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["code"] == "RESTAURANT_CLOSED"


async def test_validate_allows_inside_hours(client, auth, session, kitchen, monkeypatch):
    rid = kitchen["restaurant"].id
    for d in range(7):
        session.add(
            OpeningHour(
                restaurant_id=rid, day_of_week=d,
                opens_at=time(10, 0), closes_at=time(20, 0), is_closed=False,
            )
        )
    await session.commit()

    from app import hours as hours_mod

    monkeypatch.setattr(
        hours_mod, "local_now", lambda now=None: datetime(2026, 8, 19, 15, 0)
    )

    r = await client.post(
        f"/restaurants/{rid}/validate-order",
        json=_body(kitchen["item"].id),
        headers=auth(role="customer"),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_no_schedule_keeps_is_open_behaviour(client, auth, kitchen):
    """Without hours, a closed switch still rejects — existing flow untouched."""
    rid = kitchen["restaurant"].id
    await client.patch(
        f"/restaurants/{rid}",
        json={"is_open": False},
        headers=auth(role="restaurant", user_id=7),
    )
    r = await client.post(
        f"/restaurants/{rid}/validate-order",
        json=_body(kitchen["item"].id),
        headers=auth(role="customer"),
    )
    assert r.json()["code"] == "RESTAURANT_CLOSED"

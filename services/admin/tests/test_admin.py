"""The console: numbers assembled from copies rather than fetched from everyone.

Admin is where the split is genuinely awkward — "total GMV, user count, orders
by status" is one query in a monolith and a distributed join here. These tests
pin the arrangement that pays for it: local read-models, upserted from events,
queried without touching another service.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app import consumer, service
from app.models import OrderRow, UserRow


@pytest.fixture
async def platform(session):
    """A small platform's worth of events, as the topics would deliver them."""
    for user_id, role in ((1, "customer"), (2, "customer"), (3, "restaurant")):
        await consumer._apply_user_event(session, {
            "user_id": user_id, "role": role, "first_name": f"U{user_id}",
            "last_name": "Person", "is_active": True,
        })
    await consumer._apply_restaurant_event(session, {
        "restaurant_id": 10, "owner_id": 3, "name": "Test Kitchen",
    })
    for order_id, status, total in (
        (1, "DELIVERED", "12.00"),
        (2, "PREPARING", "20.00"),
        (3, "CANCELLED", "99.00"),
    ):
        await consumer._apply_order_event(session, {
            "order_id": order_id, "customer_id": 1, "restaurant_id": 10,
            "status": status, "total": total, "payment_status": "SUCCESS",
        })
    return session


async def test_stats_come_from_the_local_copies(session, platform):
    stats = await service.get_stats(session)
    assert stats["users"] == 3
    assert stats["restaurants"] == 1
    assert stats["orders_total"] == 3


async def test_cancelled_orders_are_not_trade(session, platform):
    """GMV excludes cancelled and rejected — the same rule the monolith had, and
    the one number an operator is most likely to be asked about."""
    stats = await service.get_stats(session)
    assert Decimal(stats["gross_merchandise_value"]) == Decimal("32.00")


async def test_orders_group_by_status(session, platform):
    stats = await service.get_stats(session)
    assert stats["orders_by_status"] == {
        "DELIVERED": 1, "PREPARING": 1, "CANCELLED": 1
    }


async def test_a_status_change_overwrites_rather_than_appends(session, platform):
    """The console reports where orders *are*. The orders service keeps the
    transition log for anyone who wants how they got there."""
    await consumer._apply_order_event(session, {
        "order_id": 2, "status": "DELIVERED",
    })
    stats = await service.get_stats(session)
    assert stats["orders_total"] == 3
    assert stats["orders_by_status"]["DELIVERED"] == 2


async def test_contact_details_arrive_on_their_own_topic(session, platform):
    """Admin is on the restricted topic because an operator looking someone up
    needs to recognise them — not because every service should be."""
    user = await session.get(UserRow, 1)
    assert user.email == ""

    await consumer._apply_contact_event(session, {
        "user_id": 1, "email": "cara@example.com", "phone": "+919876543210",
    })
    await session.refresh(user)
    assert user.email == "cara@example.com"


async def test_a_contact_event_before_the_user_event_still_works(session):
    """Topics have no ordering between them, so either can land first."""
    await consumer._apply_contact_event(session, {
        "user_id": 9, "email": "early@example.com", "phone": "+911111111111",
    })
    await consumer._apply_user_event(session, {
        "user_id": 9, "role": "customer", "first_name": "Early", "last_name": "Bird",
    })
    user = await session.get(UserRow, 9)
    assert user.email == "early@example.com"
    assert user.first_name == "Early"


async def test_replaying_every_event_changes_nothing(session, platform):
    """Every handler is an upsert keyed on the publisher's id, which is what
    makes an at-least-once stream safe to rebuild a console from."""
    before = await service.get_stats(session)

    for order_id, status, total in (
        (1, "DELIVERED", "12.00"),
        (2, "PREPARING", "20.00"),
        (3, "CANCELLED", "99.00"),
    ):
        await consumer._apply_order_event(session, {
            "order_id": order_id, "customer_id": 1, "restaurant_id": 10,
            "status": status, "total": total, "payment_status": "SUCCESS",
        })

    assert await service.get_stats(session) == before


async def test_the_order_listing_filters_and_pages(session, platform):
    delivered = await service.list_all_orders(session, status="DELIVERED")
    assert [o.id for o in delivered] == [1]

    everything = await service.list_all_orders(session, limit=2)
    assert len(everything) == 2


async def test_stats_answer_on_an_empty_platform(session):
    """A console that 500s before the first order is a console nobody trusts."""
    stats = await service.get_stats(session)
    assert stats["orders_total"] == 0
    assert Decimal(stats["gross_merchandise_value"]) == Decimal("0")


async def test_the_console_needs_the_admin_role(client, auth):
    for role in ("customer", "restaurant", "driver"):
        r = await client.get("/admin/stats", headers=auth(role=role))
        assert r.status_code == 403, role
    assert (await client.get("/admin/stats", headers=auth(role="admin"))).status_code == 200


async def test_nothing_else_reads_this_database(session, platform):
    """Every table here is a copy. If admin ever became authoritative for
    something, another service would start depending on its staleness."""
    rows = list(await session.scalars(select(OrderRow)))
    assert rows, "sanity: the fixture wrote something"
    # There is no outbox: this service publishes nothing at all.
    from app import models

    assert not hasattr(models, "OutboxEvent")

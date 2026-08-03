"""Rating aggregation: one grouped query behind every rating the UI shows."""

from decimal import Decimal

import pytest

from src.modules.reviews import ratings
from src.modules.reviews.models import Review
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import User


async def _seed(session, ratings_by_restaurant: dict[int, list[int]]):
    """Create the restaurants named by the keys, with the given review scores."""
    session.add(User(id=1, email="c@x.com", phone="+1", first_name="Alex", last_name="Rivera",
                     hashed_password="h", role="customer"))
    session.add(User(id=2, email="o@x.com", phone="+2", first_name="Ola", last_name="Owner",
                     hashed_password="h", role="restaurant"))
    order_id = 0
    for restaurant_id, scores in ratings_by_restaurant.items():
        session.add(Restaurant(id=restaurant_id, owner_id=2, name=f"R{restaurant_id}",
                               city="C", address_line="1", phone="+1",
                               min_order_amount=Decimal("0")))
        for score in scores:
            order_id += 1
            session.add(Review(order_id=order_id, customer_id=1,
                               restaurant_id=restaurant_id, rating=score))
    await session.commit()


@pytest.mark.asyncio
async def test_summary_counts_and_averages(db_session):
    await _seed(db_session, {1: [5, 4, 3]})

    summary = await ratings.summary_for_one(db_session, 1)

    assert summary.count == 3
    assert summary.average == 4.0


@pytest.mark.asyncio
async def test_average_is_rounded_to_one_decimal(db_session):
    # 5 + 4 + 4 = 13 / 3 = 4.333…
    await _seed(db_session, {1: [5, 4, 4]})

    summary = await ratings.summary_for_one(db_session, 1)

    assert summary.average == 4.3


@pytest.mark.asyncio
async def test_breakdown_counts_every_star(db_session):
    await _seed(db_session, {1: [5, 5, 3, 1]})

    summary = await ratings.summary_for_one(db_session, 1)

    assert summary.breakdown == {5: 2, 4: 0, 3: 1, 2: 0, 1: 1}


@pytest.mark.asyncio
async def test_unreviewed_restaurant_has_no_average(db_session):
    """Zero would read and sort as a terrible restaurant rather than a new one."""
    await _seed(db_session, {1: []})

    summary = await ratings.summary_for_one(db_session, 1)

    assert summary.average is None
    assert summary.count == 0
    assert summary.breakdown == {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}


@pytest.mark.asyncio
async def test_several_restaurants_are_summarised_together(db_session):
    await _seed(db_session, {1: [5, 5], 2: [2], 3: []})

    summaries = await ratings.summary_for(db_session, [1, 2, 3])

    assert summaries[1].average == 5.0 and summaries[1].count == 2
    assert summaries[2].average == 2.0 and summaries[2].count == 1
    assert summaries[3].average is None and summaries[3].count == 0


@pytest.mark.asyncio
async def test_every_requested_id_is_present(db_session):
    """Callers must never have to guard against a missing key."""
    await _seed(db_session, {1: [4]})

    summaries = await ratings.summary_for(db_session, [1, 999])

    assert set(summaries) == {1, 999}
    assert summaries[999].count == 0


@pytest.mark.asyncio
async def test_no_ids_needs_no_query(db_session):
    assert await ratings.summary_for(db_session, []) == {}


@pytest.mark.asyncio
async def test_reviews_of_other_restaurants_are_not_mixed_in(db_session):
    await _seed(db_session, {1: [5, 5, 5], 2: [1]})

    summary = await ratings.summary_for_one(db_session, 2)

    assert summary.count == 1
    assert summary.average == 1.0

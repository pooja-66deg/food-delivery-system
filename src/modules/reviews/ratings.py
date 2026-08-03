"""Rating aggregation for restaurants.

Computed on read from a single grouped query rather than kept in denormalised
counters: reviews only exist for delivered orders, so the table is small, and a
rating that has silently drifted is worse than one that costs a query.
"""

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reviews.models import Review

STARS = (5, 4, 3, 2, 1)


@dataclass(frozen=True)
class RatingSummary:
    """What a restaurant's reviews add up to.

    ``average`` is None when there are no reviews — not 0.0, which would read
    and sort as a terrible restaurant rather than a new one.
    """

    average: float | None
    count: int
    breakdown: dict[int, int]


EMPTY = RatingSummary(average=None, count=0, breakdown={star: 0 for star in STARS})


def _summarise(counts: dict[int, int]) -> RatingSummary:
    breakdown = {star: counts.get(star, 0) for star in STARS}
    count = sum(breakdown.values())
    if count == 0:
        return EMPTY
    total = sum(star * n for star, n in breakdown.items())
    # One decimal place — the precision the UI shows.
    return RatingSummary(average=round(total / count, 1), count=count, breakdown=breakdown)


async def summary_for(
    session: AsyncSession, restaurant_ids: Sequence[int]
) -> dict[int, RatingSummary]:
    """Summarise several restaurants at once.

    One query however many ids are passed, so a browse page costs the same as a
    single restaurant. Every requested id is present in the result — an
    unreviewed one maps to an empty summary, so callers never guard for a
    missing key.
    """
    if not restaurant_ids:
        return {}

    stmt = (
        select(Review.restaurant_id, Review.rating, func.count(Review.id))
        .where(Review.restaurant_id.in_(restaurant_ids))
        .group_by(Review.restaurant_id, Review.rating)
    )
    counts: dict[int, dict[int, int]] = {}
    for restaurant_id, rating, total in await session.execute(stmt):
        counts.setdefault(restaurant_id, {})[rating] = total

    return {rid: _summarise(counts.get(rid, {})) for rid in restaurant_ids}


async def summary_for_one(session: AsyncSession, restaurant_id: int) -> RatingSummary:
    """Summarise a single restaurant."""
    summaries = await summary_for(session, [restaurant_id])
    return summaries.get(restaurant_id, EMPTY)

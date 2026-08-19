"""Restaurant discovery: dish-aware search, facet filters, sorting, paging.

Kept apart from ``service.py`` because this is one query assembled from many
optional clauses, and the rules that make it correct are worth stating in one
place:

- **Search reaches the menu.** "biryani" is a dish, not a restaurant name, and a
  search that only matched restaurant names would find nothing for it. A hit on
  a menu item counts as a hit on its restaurant, and the matching dish names ride
  back on the result so the UI can say *why* a restaurant appeared.
- **Aggregates come from subqueries, not from the rows.** Rating and price live in
  reviews and menu_items, so filtering or sorting on them needs the aggregate
  joined in — computing it per row in Python would make paging meaningless,
  because you cannot page a set you have not finished filtering.
- **An unrated restaurant is not a nought-star restaurant.** Sorting by rating
  puts unrated ones last rather than at the bottom of the scale, which is where
  a COALESCE to 0 would file them.
- **Only available items count.** A filter is a promise about what can be ordered
  now; a sold-out dish keeping a restaurant in the vegetarian results breaks it.
- **Only approved restaurants are discoverable.** Owners register themselves, so
  this is the boundary between "a row exists" and "a customer may see it". It is
  applied unconditionally rather than as another optional filter — an operator
  forgetting to pass it must not be able to leak an unvetted venue.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import hours as hours_mod
from app.models import APPROVED, MenuItem, Restaurant
from app.models import Review

# Price bands as upper bounds on a restaurant's average available-item price.
# Band 3 is everything above the last bound.
PRICE_BAND_BOUNDS = ((1, Decimal("10")), (2, Decimal("25")))
MAX_PRICE_BAND = 3

SORTS = ("name", "rating", "price_low", "price_high")
DEFAULT_SORT = "name"

# Paging defaults. The browse endpoint used to return every row; a page size is
# what stops one city's growth from becoming a latency cliff.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class SearchResult:
    """One page of restaurants, plus the size of the whole matching set."""

    items: list[Restaurant]
    total: int


def _rating_aggregate():
    """Average rating and review count per restaurant."""
    return (
        select(
            Review.restaurant_id.label("restaurant_id"),
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.restaurant_id)
        .subquery()
    )


def _price_aggregate():
    """Average price of the items a customer could actually order."""
    return (
        select(
            MenuItem.restaurant_id.label("restaurant_id"),
            func.avg(MenuItem.price).label("avg_price"),
        )
        .where(MenuItem.is_available.is_(True))
        .group_by(MenuItem.restaurant_id)
        .subquery()
    )


def _dish_match(term: str):
    """Restaurant ids whose menu has an available item matching ``term``."""
    pattern = f"%{term}%"
    return (
        select(MenuItem.restaurant_id)
        .where(MenuItem.is_available.is_(True), MenuItem.name.ilike(pattern))
        .distinct()
    )


#: What the Vegetarian filter accepts. A "both" kitchen is excluded on purpose:
#: a customer filtering for vegetarian is asking for a vegetarian restaurant,
#: not for one that has vegetarian options.
VEGETARIAN_FOOD_TYPES = ("veg",)


def band_range(band: int) -> tuple[Decimal, Decimal | None]:
    """The ``[lower, upper)`` average-price window for a band.

    ``upper`` is None for the top band, which is unbounded. With bounds of
    (10, 25) the windows are band 1 = [0, 10), band 2 = [10, 25), band 3 = [25, ∞).
    """
    uppers = [upper for _, upper in PRICE_BAND_BOUNDS]
    if band <= 1:
        return Decimal("0"), uppers[0]
    if band <= len(uppers):
        return uppers[band - 2], uppers[band - 1]
    return uppers[-1], None


def _price_band_clause(avg_price, band: int):
    """Bound the average price to the requested band."""
    lower, upper = band_range(band)
    if upper is None:
        return avg_price >= lower
    return and_(avg_price >= lower, avg_price < upper)


def band_for_price(avg_price: Decimal | float | None) -> int | None:
    """Which band an average price falls in, or None when there is no menu."""
    if avg_price is None:
        return None
    price = Decimal(str(avg_price))
    for band, upper in PRICE_BAND_BOUNDS:
        if price < upper:
            return band
    return MAX_PRICE_BAND


def _apply_sort(stmt: Select, sort: str, avg_rating, review_count, avg_price) -> Select:
    if sort == "rating":
        # Unrated last: nulls_last() rather than coalescing to 0, which would
        # file a brand-new restaurant below a genuinely bad one. Review count
        # breaks ties so 5.0-from-one-review does not outrank 4.8-from-two-hundred.
        return stmt.order_by(
            avg_rating.desc().nulls_last(), review_count.desc().nulls_last(), Restaurant.name
        )
    if sort == "price_low":
        return stmt.order_by(avg_price.asc().nulls_last(), Restaurant.name)
    if sort == "price_high":
        return stmt.order_by(avg_price.desc().nulls_last(), Restaurant.name)
    return stmt.order_by(Restaurant.name)


async def search(
    session: AsyncSession,
    *,
    city: str | None = None,
    search: str | None = None,
    cuisine: str | None = None,
    min_rating: float | None = None,
    price_band: int | None = None,
    vegetarian_only: bool = False,
    open_only: bool = False,
    sort: str = DEFAULT_SORT,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> SearchResult:
    """One page of restaurants matching every supplied filter."""
    ratings = _rating_aggregate()
    prices = _price_aggregate()
    avg_rating = ratings.c.avg_rating
    review_count = ratings.c.review_count
    avg_price = prices.c.avg_price

    base = (
        select(Restaurant)
        .outerjoin(ratings, ratings.c.restaurant_id == Restaurant.id)
        .outerjoin(prices, prices.c.restaurant_id == Restaurant.id)
    )

    # First and unconditional: browse is the customer-facing surface, and an
    # unapproved venue must never reach it. Not a parameter, so no caller can
    # omit it.
    conditions = [Restaurant.approval_status == APPROVED]
    if city and city.strip():
        conditions.append(Restaurant.city.ilike(f"%{city.strip()}%"))
    if cuisine and cuisine.strip():
        conditions.append(Restaurant.cuisine.ilike(f"%{cuisine.strip()}%"))
    if search and search.strip():
        term = search.strip()
        pattern = f"%{term}%"
        conditions.append(
            or_(
                Restaurant.name.ilike(pattern),
                Restaurant.cuisine.ilike(pattern),
                Restaurant.id.in_(_dish_match(term)),
            )
        )
    if min_rating is not None:
        # An unrated restaurant cannot satisfy a rating floor, and the NULL from
        # the outer join drops it here without needing an explicit is-not-null.
        conditions.append(avg_rating >= min_rating)
    if price_band is not None:
        conditions.append(_price_band_clause(avg_price, price_band))
    if vegetarian_only:
        conditions.append(Restaurant.food_type.in_(VEGETARIAN_FOOD_TYPES))
    if open_only:
        # Manual switch still required; schedule only tightens it when present.
        conditions.append(Restaurant.is_open.is_(True))
        conditions.append(hours_mod.within_schedule_clause())

    if conditions:
        base = base.where(and_(*conditions))

    # Count before paging: the UI needs the size of the whole match, not of the
    # page. Built from the same joins and filters so the two cannot disagree.
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )

    paged = _apply_sort(base, sort, avg_rating, review_count, avg_price)
    paged = paged.limit(max(1, min(limit, MAX_LIMIT))).offset(max(0, offset))
    items = list(await session.scalars(paged))
    return SearchResult(items=items, total=total or 0)


async def attach_price_bands(session: AsyncSession, restaurants: Sequence[Restaurant]) -> None:
    """Set ``price_band`` on each restaurant for the response schema to read.

    One query for the page, matching how ratings are attached. A restaurant with
    no available items has no band rather than a cheap one — nothing to price.
    """
    if not restaurants:
        return
    ids = [r.id for r in restaurants]
    stmt = (
        select(MenuItem.restaurant_id, func.avg(MenuItem.price))
        .where(MenuItem.restaurant_id.in_(ids), MenuItem.is_available.is_(True))
        .group_by(MenuItem.restaurant_id)
    )
    averages = {rid: avg for rid, avg in await session.execute(stmt)}
    for restaurant in restaurants:
        restaurant.price_band = band_for_price(averages.get(restaurant.id))


async def attach_matched_items(
    session: AsyncSession, restaurants: Sequence[Restaurant], search: str | None
) -> None:
    """Name the dishes that made each restaurant match, for the UI to show.

    Without this, a search for "biryani" returns a restaurant whose name and
    cuisine say nothing about biryani and the customer cannot tell why it is
    there. Skipped entirely when there is no search term, since then nothing
    matched in particular.
    """
    for restaurant in restaurants:
        restaurant.matched_items = []
    if not restaurants or not (search and search.strip()):
        return

    ids = [r.id for r in restaurants]
    stmt = (
        select(MenuItem.restaurant_id, MenuItem.name)
        .where(
            MenuItem.restaurant_id.in_(ids),
            MenuItem.is_available.is_(True),
            MenuItem.name.ilike(f"%{search.strip()}%"),
        )
        .order_by(MenuItem.restaurant_id, MenuItem.name)
    )
    by_restaurant: dict[int, list[str]] = {}
    for restaurant_id, name in await session.execute(stmt):
        by_restaurant.setdefault(restaurant_id, []).append(name)
    for restaurant in restaurants:
        restaurant.matched_items = by_restaurant.get(restaurant.id, [])

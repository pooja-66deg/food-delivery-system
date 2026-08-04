"""Discovery: dish-aware search, facet filters, sorting, and paging."""
from decimal import Decimal

import pytest

from src.modules.restaurants import discovery, menu, service
from src.modules.restaurants.schemas import CategoryCreate, MenuItemCreate, RestaurantCreate
from src.modules.reviews.models import Review
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister

_PHONE = iter(range(10000, 99999))


async def _owner(db_session, email="disc-owner@example.com"):
    return await users_service.register_user(
        db_session,
        UserRegister(email=email, phone=f"+1555{next(_PHONE)}", first_name="O", last_name="W",
                     password="supersecret1", role="restaurant"),
    )


async def _restaurant(db_session, owner, name, *, city="Metropolis", cuisine=None, is_open=True):
    r = await service.create_restaurant(
        db_session, owner,
        RestaurantCreate(name=name, city=city, cuisine=cuisine, address_line="1 St",
                         phone="+15550000000"),
    )
    if is_open:
        r.is_open = True
        await db_session.commit()
    return r


async def _item(db_session, owner, restaurant, name, price, *, vegetarian=False, available=True):
    category = await menu.add_category(
        db_session, owner, restaurant.id, CategoryCreate(name=f"Cat {name}")
    )
    return await menu.add_item(
        db_session, owner, restaurant.id,
        MenuItemCreate(category_id=category.id, name=name, price=Decimal(price),
                       is_available=available, is_vegetarian=vegetarian),
    )


async def _rate(db_session, restaurant, ratings):
    """Attach reviews to a restaurant. Order/customer ids are not read by the
    rating aggregate, so distinct placeholders are enough."""
    for i, rating in enumerate(ratings):
        db_session.add(Review(order_id=restaurant.id * 1000 + i, customer_id=1,
                              restaurant_id=restaurant.id, rating=rating))
    await db_session.commit()


async def _browse(db_session, **filters):
    return await discovery.search(db_session, **filters)


# ---------- dish-level search ----------

@pytest.mark.asyncio
async def test_search_finds_a_restaurant_by_a_dish_on_its_menu(db_session):
    """"biryani" is a dish, not a restaurant name — the whole point of the feature."""
    owner = await _owner(db_session)
    spice = await _restaurant(db_session, owner, "Spice Room", cuisine="Indian")
    await _restaurant(db_session, owner, "Taco Stand", cuisine="Mexican")
    await _item(db_session, owner, spice, "Chicken Biryani", "12.00")

    found = await _browse(db_session, search="biryani")

    assert [r.name for r in found.items] == ["Spice Room"]


@pytest.mark.asyncio
async def test_search_still_matches_restaurant_name_and_cuisine(db_session):
    owner = await _owner(db_session)
    await _restaurant(db_session, owner, "Pizza Palace", cuisine="Italian")
    await _restaurant(db_session, owner, "Sushi Spot", cuisine="Japanese")

    assert [r.name for r in (await _browse(db_session, search="pizza")).items] == ["Pizza Palace"]
    assert [r.name for r in (await _browse(db_session, search="japanese")).items] == ["Sushi Spot"]


@pytest.mark.asyncio
async def test_a_dish_that_is_unavailable_does_not_surface_its_restaurant(db_session):
    """A filter is a promise about what can be ordered now."""
    owner = await _owner(db_session)
    spice = await _restaurant(db_session, owner, "Spice Room")
    await _item(db_session, owner, spice, "Chicken Biryani", "12.00", available=False)

    assert (await _browse(db_session, search="biryani")).items == []


@pytest.mark.asyncio
async def test_a_restaurant_matched_by_a_dish_reports_which_dish(db_session):
    """Otherwise the customer cannot tell why the result is in the list."""
    owner = await _owner(db_session)
    spice = await _restaurant(db_session, owner, "Spice Room")
    await _item(db_session, owner, spice, "Chicken Biryani", "12.00")
    await _item(db_session, owner, spice, "Veg Biryani", "10.00", vegetarian=True)
    await _item(db_session, owner, spice, "Naan", "3.00")

    found = await _browse(db_session, search="biryani")
    await discovery.attach_matched_items(db_session, found.items, "biryani")

    assert found.items[0].matched_items == ["Chicken Biryani", "Veg Biryani"]


@pytest.mark.asyncio
async def test_matched_items_is_empty_without_a_search_term(db_session):
    owner = await _owner(db_session)
    spice = await _restaurant(db_session, owner, "Spice Room")
    await _item(db_session, owner, spice, "Chicken Biryani", "12.00")

    found = await _browse(db_session)
    await discovery.attach_matched_items(db_session, found.items, None)

    assert found.items[0].matched_items == []


# ---------- vegetarian filter ----------

@pytest.mark.asyncio
async def test_vegetarian_filter_keeps_only_restaurants_with_a_veg_dish(db_session):
    owner = await _owner(db_session)
    veg = await _restaurant(db_session, owner, "Green Bowl")
    meat = await _restaurant(db_session, owner, "Grill House")
    await _item(db_session, owner, veg, "Paneer Tikka", "9.00", vegetarian=True)
    await _item(db_session, owner, meat, "Lamb Chops", "18.00")

    found = await _browse(db_session, vegetarian_only=True)

    assert [r.name for r in found.items] == ["Green Bowl"]


@pytest.mark.asyncio
async def test_an_unlabelled_dish_does_not_count_as_vegetarian(db_session):
    """Unlabelled has to read as "not vegetarian", or the filter misleads a diner."""
    owner = await _owner(db_session)
    unknown = await _restaurant(db_session, owner, "Mystery Kitchen")
    await _item(db_session, owner, unknown, "Chef's Special", "11.00")

    assert (await _browse(db_session, vegetarian_only=True)).items == []


@pytest.mark.asyncio
async def test_a_sold_out_veg_dish_does_not_keep_a_restaurant_in_the_results(db_session):
    owner = await _owner(db_session)
    veg = await _restaurant(db_session, owner, "Green Bowl")
    await _item(db_session, owner, veg, "Paneer Tikka", "9.00", vegetarian=True, available=False)

    assert (await _browse(db_session, vegetarian_only=True)).items == []


# ---------- rating filter and sort ----------

@pytest.mark.asyncio
async def test_min_rating_excludes_lower_rated_restaurants(db_session):
    owner = await _owner(db_session)
    good = await _restaurant(db_session, owner, "Good Eats")
    poor = await _restaurant(db_session, owner, "Poor Eats")
    await _rate(db_session, good, [5, 4])       # 4.5
    await _rate(db_session, poor, [2, 3])       # 2.5

    found = await _browse(db_session, min_rating=4)

    assert [r.name for r in found.items] == ["Good Eats"]


@pytest.mark.asyncio
async def test_an_unrated_restaurant_cannot_satisfy_a_rating_floor(db_session):
    owner = await _owner(db_session)
    await _restaurant(db_session, owner, "Brand New")

    assert (await _browse(db_session, min_rating=4)).items == []


@pytest.mark.asyncio
async def test_rating_sort_puts_unrated_last_not_bottom_of_the_scale(db_session):
    """A brand-new restaurant must not be filed below a genuinely bad one."""
    owner = await _owner(db_session)
    fresh = await _restaurant(db_session, owner, "Brand New")
    bad = await _restaurant(db_session, owner, "Bad Eats")
    great = await _restaurant(db_session, owner, "Great Eats")
    await _rate(db_session, bad, [1])
    await _rate(db_session, great, [5])

    found = await _browse(db_session, sort="rating")

    assert [r.name for r in found.items] == ["Great Eats", "Bad Eats", "Brand New"]
    assert fresh.id == found.items[-1].id


@pytest.mark.asyncio
async def test_rating_sort_breaks_ties_on_review_count(db_session):
    """5.0 from one review should not outrank 5.0 from many."""
    owner = await _owner(db_session)
    lone = await _restaurant(db_session, owner, "A Lone Review")
    many = await _restaurant(db_session, owner, "B Many Reviews")
    await _rate(db_session, lone, [5])
    await _rate(db_session, many, [5, 5, 5])

    found = await _browse(db_session, sort="rating")

    assert [r.name for r in found.items] == ["B Many Reviews", "A Lone Review"]


# ---------- price band ----------

@pytest.mark.parametrize(
    "average, expected",
    [("5.00", 1), ("9.99", 1), ("10.00", 2), ("24.99", 2), ("25.00", 3), ("80.00", 3)],
)
def test_band_for_price_maps_the_boundaries(average, expected):
    assert discovery.band_for_price(Decimal(average)) == expected


def test_band_for_price_is_none_without_a_menu():
    """No orderable items means nothing to price, not "cheap"."""
    assert discovery.band_for_price(None) is None


@pytest.mark.asyncio
async def test_price_band_filter_selects_by_average_item_price(db_session):
    owner = await _owner(db_session)
    cheap = await _restaurant(db_session, owner, "Cheap Bites")
    fancy = await _restaurant(db_session, owner, "Fancy Plates")
    await _item(db_session, owner, cheap, "Roll", "5.00")
    await _item(db_session, owner, fancy, "Tasting Menu", "60.00")

    assert [r.name for r in (await _browse(db_session, price_band=1)).items] == ["Cheap Bites"]
    assert [r.name for r in (await _browse(db_session, price_band=3)).items] == ["Fancy Plates"]


@pytest.mark.asyncio
async def test_price_sort_orders_by_average_price(db_session):
    owner = await _owner(db_session)
    cheap = await _restaurant(db_session, owner, "Cheap Bites")
    mid = await _restaurant(db_session, owner, "Mid Range")
    await _item(db_session, owner, cheap, "Roll", "5.00")
    await _item(db_session, owner, mid, "Bowl", "15.00")

    low = await _browse(db_session, sort="price_low")
    high = await _browse(db_session, sort="price_high")

    assert [r.name for r in low.items] == ["Cheap Bites", "Mid Range"]
    assert [r.name for r in high.items] == ["Mid Range", "Cheap Bites"]


@pytest.mark.asyncio
async def test_attach_price_bands_sets_the_band_for_the_page(db_session):
    owner = await _owner(db_session)
    cheap = await _restaurant(db_session, owner, "Cheap Bites")
    empty = await _restaurant(db_session, owner, "No Menu Yet")
    await _item(db_session, owner, cheap, "Roll", "5.00")

    found = await _browse(db_session)
    await discovery.attach_price_bands(db_session, found.items)

    bands = {r.name: r.price_band for r in found.items}
    assert bands["Cheap Bites"] == 1
    assert bands["No Menu Yet"] is None
    assert empty.id in {r.id for r in found.items}


# ---------- open filter, paging, totals ----------

@pytest.mark.asyncio
async def test_open_only_filter(db_session):
    owner = await _owner(db_session)
    await _restaurant(db_session, owner, "Open Now", is_open=True)
    await _restaurant(db_session, owner, "Shut", is_open=False)

    assert [r.name for r in (await _browse(db_session, open_only=True)).items] == ["Open Now"]


@pytest.mark.asyncio
async def test_unfiltered_browse_returns_everything_within_the_page(db_session):
    owner = await _owner(db_session)
    for name in ("A", "B", "C"):
        await _restaurant(db_session, owner, name)

    found = await _browse(db_session)

    assert len(found.items) == 3
    assert found.total == 3


@pytest.mark.asyncio
async def test_paging_walks_the_result_set_and_total_covers_the_whole_match(db_session):
    owner = await _owner(db_session)
    for i in range(5):
        await _restaurant(db_session, owner, f"R{i}")

    first = await _browse(db_session, limit=2, offset=0)
    second = await _browse(db_session, limit=2, offset=2)
    last = await _browse(db_session, limit=2, offset=4)

    assert [r.name for r in first.items] == ["R0", "R1"]
    assert [r.name for r in second.items] == ["R2", "R3"]
    assert [r.name for r in last.items] == ["R4"]
    # The total is the size of the match, not of the page — that is what lets a
    # client tell a last page from a truncated one.
    assert first.total == second.total == last.total == 5


@pytest.mark.asyncio
async def test_total_reflects_the_filters_not_the_whole_table(db_session):
    owner = await _owner(db_session)
    await _restaurant(db_session, owner, "Metro One", city="Metropolis")
    await _restaurant(db_session, owner, "Metro Two", city="Metropolis")
    await _restaurant(db_session, owner, "Gotham One", city="Gotham")

    found = await _browse(db_session, city="Metropolis", limit=1)

    assert len(found.items) == 1
    assert found.total == 2


@pytest.mark.asyncio
async def test_limit_is_capped(db_session):
    """A client cannot ask for the whole table by sending a huge limit."""
    owner = await _owner(db_session)
    await _restaurant(db_session, owner, "Only One")

    found = await _browse(db_session, limit=10_000)

    assert len(found.items) == 1  # capped, but the page still fits what exists


@pytest.mark.asyncio
async def test_filters_combine(db_session):
    owner = await _owner(db_session)
    match = await _restaurant(db_session, owner, "Green Metro", city="Metropolis")
    wrong_city = await _restaurant(db_session, owner, "Green Gotham", city="Gotham")
    await _item(db_session, owner, match, "Veg Bowl", "8.00", vegetarian=True)
    await _item(db_session, owner, wrong_city, "Veg Bowl", "8.00", vegetarian=True)
    await _rate(db_session, match, [5])
    await _rate(db_session, wrong_city, [5])

    found = await _browse(
        db_session, city="Metropolis", vegetarian_only=True, min_rating=4,
        price_band=1, open_only=True, sort="rating",
    )

    assert [r.name for r in found.items] == ["Green Metro"]

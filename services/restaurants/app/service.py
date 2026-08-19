"""Business logic for restaurant profiles."""

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app import hours as hours_mod
from app import outbox
from app.config import settings
from app.models import APPROVED, PENDING, REJECTED, OpeningHour, OwnerRow, Restaurant
from app.schemas import OpeningHourDay, RestaurantCreate, RestaurantUpdate
from app import ratings
from shared.identity import Identity


async def owned_by(session: AsyncSession, owner_id: int) -> list[Restaurant]:
    """Every restaurant this owner has, whatever its approval status.

    The owner dashboard's source of truth. It cannot use browse: browse shows
    only approved venues, so an owner waiting on approval would look at an empty
    dashboard and reasonably conclude their registration was lost.
    """
    stmt = select(Restaurant).where(Restaurant.owner_id == owner_id).order_by(Restaurant.id)
    return list(await session.scalars(stmt))


async def register_from_signup(session: AsyncSession, payload: dict) -> Restaurant | None:
    """Create the pending venue for someone who has just signed up as an owner.

    The counterpart to create_restaurant, for the path where the owner cannot
    call an API: business details are collected during registration precisely
    because the account is inactive until an operator approves, so there is no
    token to authenticate a normal create with. The users service records the
    details in the same transaction as the account and this turns them into a
    restaurant.

    Returns None when the owner already has one. That is the idempotency the
    at-least-once transport requires — a redelivered registration must not create
    a second venue — and it doubles as the same one-restaurant-per-owner rule
    create_restaurant enforces, arrived at from the other direction.
    """
    owner_id = payload.get("owner_id")
    name = payload.get("name")
    if owner_id is None or not name:
        # Nothing recoverable here. The caller acknowledges rather than retries:
        # a payload this shape will never become valid, and redelivering it
        # forever would block every registration queued behind it.
        return None

    if await owned_by(session, owner_id):
        return None

    restaurant = Restaurant(
        owner_id=owner_id,
        name=name,
        city=payload.get("city") or "",
        address_line=payload.get("address_line") or "",
        phone=payload.get("phone") or "",
        cuisine=payload.get("cuisine"),
        description=payload.get("description"),
        food_type=payload.get("food_type") or "both",
        # The same rule as create_restaurant, for the same reason — and here the
        # applicant's account is inactive until this row is approved, so it is
        # also what is keeping them out.
        approval_status=PENDING,
    )
    session.add(restaurant)
    await session.flush()  # assigns restaurant.id, which the event needs
    publish_restaurant(session, restaurant)
    alert_admin_of_submission(session, restaurant)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


def alert_admin_of_submission(session: AsyncSession, restaurant: Restaurant) -> None:
    """Tell the operator there is something waiting for them.

    Without this, approval is a queue nobody is told about: the applicant is
    locked out until a decision is made, and the only way anyone learns a
    decision is due is by opening the console and looking. A registration on a
    Friday evening would sit until somebody happened to check.

    Addressed to a configured mailbox rather than to admin users individually,
    because this service does not know who the admins are — roles live in the
    users service and their addresses only in notifications. The direct
    notification topic already accepts a plain address for exactly this case, so
    an operations mailbox needs no new machinery and no copy of anyone's
    contact details here.

    Unset means no alert, and that is a supported state: the console still lists
    everything pending, so an unconfigured deployment is one where the operator
    polls rather than one that loses registrations.
    """
    if not settings.admin_alert_email:
        return
    outbox.record_event(
        session, "notification-events", str(restaurant.id),
        {
            "channel": "EMAIL",
            "to": settings.admin_alert_email,
            "type": "restaurant_pending",
            "subject": f"New restaurant awaiting approval: {restaurant.name}",
            "message": (
                f"{restaurant.name} registered in {restaurant.city} and is "
                f"waiting for approval. The owner cannot sign in until it is "
                f"reviewed. Open the admin console to approve or reject it."
            ),
        },
    )


async def create_restaurant(session: AsyncSession, owner: Identity, data: RestaurantCreate) -> Restaurant:
    """Register a venue for this owner. One each.

    The limit is enforced here rather than by a unique constraint on owner_id,
    because it is a product rule and not a data-integrity one — the schema is
    already able to represent an owner with several, and lifting the rule later
    should not need a migration.
    """
    existing = await owned_by(session, owner.user_id)
    if existing:
        raise ConflictException(
            "You already manage a restaurant. One account manages one restaurant."
        )

    restaurant = Restaurant(
        owner_id=owner.user_id,
        # Not from the payload: an owner who could post their own status would
        # approve themselves, which is the entire thing approval exists to stop.
        approval_status=PENDING,
        **data.model_dump(),
    )
    session.add(restaurant)
    await session.flush()  # assigns restaurant.id, which the event needs
    publish_restaurant(session, restaurant)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


async def set_approval(
    session: AsyncSession, restaurant_id: int, status: str, reason: str | None = None
) -> Restaurant:
    """Approve or reject a restaurant. Admin-only — the router enforces that.

    The reason is cleared on approval rather than kept as history: it is shown
    to the owner as "why you are rejected", and a stale one displayed beside an
    approved venue would be actively misleading.
    """
    restaurant = await get_restaurant(session, restaurant_id)
    restaurant.approval_status = status
    restaurant.rejection_reason = reason if status == REJECTED else None
    # A rejected venue must not keep taking orders. Approving does not set
    # is_open, though — when the kitchen opens is the owner's call, not ours.
    if status != APPROVED:
        restaurant.is_open = False
    publish_restaurant(session, restaurant)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


@dataclass(frozen=True)
class AdminList:
    """One page of the admin restaurant list, plus the whole match count."""

    items: list[Restaurant]
    total: int


async def admin_list(
    session: AsyncSession,
    *,
    approval_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> AdminList:
    """Every restaurant, newest first, for the operator console.

    Newest first rather than alphabetical, unlike browse: the operator's job on
    this screen is to work through what has just arrived, and a pending venue
    registered this morning sorting under "Z" is one they never see.

    No approval predicate unless asked for one — this is the one read on the
    platform that is *supposed* to see unapproved venues.
    """
    stmt = select(Restaurant)
    count_stmt = select(func.count(Restaurant.id))
    if approval_status:
        stmt = stmt.where(Restaurant.approval_status == approval_status)
        count_stmt = count_stmt.where(Restaurant.approval_status == approval_status)

    total = await session.scalar(count_stmt) or 0
    stmt = stmt.order_by(Restaurant.created_at.desc(), Restaurant.id.desc())
    items = list(await session.scalars(stmt.limit(limit).offset(offset)))
    return AdminList(items=items, total=total)


async def attach_owner_names(session: AsyncSession, restaurants: Sequence[Restaurant]) -> None:
    """Set ``owner_name`` on each restaurant for the admin list to read.

    One query for the page. An owner with no local row — registered before this
    read-model existed, or an event not yet consumed — reads as empty rather
    than dropping the restaurant from the list: an operator needs to see a venue
    they cannot yet name far more than they need the name.
    """
    if not restaurants:
        return
    owner_ids = {r.owner_id for r in restaurants}
    rows = await session.scalars(select(OwnerRow).where(OwnerRow.id.in_(owner_ids)))
    names = {row.id: f"{row.first_name} {row.last_name}".strip() for row in rows}
    for restaurant in restaurants:
        restaurant.owner_name = names.get(restaurant.owner_id) or ""


async def get_restaurant(session: AsyncSession, restaurant_id: int) -> Restaurant:
    restaurant = await session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise NotFoundException("Restaurant", str(restaurant_id))
    return restaurant


async def attach_ratings(session: AsyncSession, restaurants: Sequence[Restaurant]) -> None:
    """Set each restaurant's rating fields for the response schemas to read.

    Called explicitly by the browse and detail routes rather than from
    ``get_restaurant``, which checkout also uses and has no need for ratings.
    One query for the whole page.
    """
    if not restaurants:
        return
    summaries = await ratings.summary_for(session, [r.id for r in restaurants])
    for restaurant in restaurants:
        summary = summaries.get(restaurant.id, ratings.EMPTY)
        restaurant.rating_average = summary.average
        restaurant.review_count = summary.count
        restaurant.rating_breakdown = summary.breakdown


def _hour_to_schema(row: OpeningHour) -> OpeningHourDay:
    return OpeningHourDay(
        day_of_week=row.day_of_week,
        opens_at=hours_mod.format_hhmm(row.opens_at),
        closes_at=hours_mod.format_hhmm(row.closes_at),
        is_closed=row.is_closed,
    )


async def opening_hours_for(
    session: AsyncSession, restaurant_id: int
) -> list[OpeningHour]:
    """One restaurant's schedule in weekday order."""
    return list(
        await session.scalars(
            select(OpeningHour)
            .where(OpeningHour.restaurant_id == restaurant_id)
            .order_by(OpeningHour.day_of_week)
        )
    )


async def attach_opening_hours(
    session: AsyncSession, restaurants: Sequence[Restaurant]
) -> None:
    """Attach weekly hours and the derived accepting-orders flag.

    One query for the page. Restaurants with no rows get an empty schedule and
    ``is_accepting_orders == is_open``, which is the pre-schedule behaviour.
    """
    if not restaurants:
        return

    ids = [r.id for r in restaurants]
    rows = list(
        await session.scalars(select(OpeningHour).where(OpeningHour.restaurant_id.in_(ids)))
    )
    by_restaurant: dict[int, list[OpeningHour]] = {}
    for row in rows:
        by_restaurant.setdefault(row.restaurant_id, []).append(row)

    for restaurant in restaurants:
        schedule = by_restaurant.get(restaurant.id, [])
        schedule.sort(key=lambda r: r.day_of_week)
        status = hours_mod.schedule_status(restaurant.is_open, schedule)
        restaurant.opening_hours = [_hour_to_schema(r) for r in schedule]
        restaurant.is_accepting_orders = status.accepting_orders
        restaurant.local_day_of_week = status.local_day_of_week
        restaurant.current_closes_at = hours_mod.format_hhmm(status.current_closes_at)
        restaurant.open_24_hours = status.open_24_hours
        restaurant.next_opens_at = hours_mod.format_hhmm(status.next_opens_at)
        restaurant.next_opens_day = status.next_opens_day


async def replace_opening_hours(
    session: AsyncSession, restaurant_id: int, days: list[OpeningHourDay]
) -> None:
    """Replace the whole weekly schedule for one restaurant.

    Delete-then-insert rather than upsert: the payload is the full week the
    owner just edited, and partial merges would leave stale days behind.
    """
    existing = await opening_hours_for(session, restaurant_id)
    for row in existing:
        await session.delete(row)
    await session.flush()

    for day in days:
        session.add(
            OpeningHour(
                restaurant_id=restaurant_id,
                day_of_week=day.day_of_week,
                opens_at=hours_mod.parse_hhmm(day.opens_at),
                closes_at=hours_mod.parse_hhmm(day.closes_at),
                is_closed=day.is_closed,
            )
        )


# Shortest term that earns a suggestion lookup — one character matches most of
# the table and is never a useful hint.
SUGGEST_MIN_CHARS = 2


def _matches_term(term: str):
    """Name-or-cuisine predicate shared by browse and suggest.

    Both paths use it so a suggestion can never appear that pressing Search
    then fails to return. `cuisine` is nullable, but `NULL ILIKE x` is NULL
    rather than true, so untagged restaurants drop out without a COALESCE.
    """
    pattern = f"%{term}%"
    return or_(Restaurant.name.ilike(pattern), Restaurant.cuisine.ilike(pattern))


async def suggest_restaurants(
    session: AsyncSession, q: str, limit: int = 8
) -> list[Restaurant]:
    """Typeahead hits for a partial query. Empty below SUGGEST_MIN_CHARS."""
    term = (q or "").strip()
    if len(term) < SUGGEST_MIN_CHARS:
        return []
    stmt = (
        select(Restaurant)
        # Same approval gate as browse. A suggestion for a venue that browse
        # then refuses to return is worse than no suggestion — the customer
        # reads it as the search being broken.
        .where(Restaurant.approval_status == APPROVED, _matches_term(term))
        .order_by(Restaurant.name)
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def popular_cuisines(session: AsyncSession, limit: int = 8) -> list[tuple[str, int]]:
    """Cuisines by restaurant count, busiest first.

    Ties break on name so the ordering is deterministic and tests are stable.
    """
    count = func.count(Restaurant.id)
    stmt = (
        select(Restaurant.cuisine, count)
        # Approved only: these counts are a customer-facing facet, so an
        # unapproved venue must not inflate one and advertise a cuisine that
        # browse has nothing to show for.
        .where(
            Restaurant.approval_status == APPROVED,
            Restaurant.cuisine.isnot(None),
            Restaurant.cuisine != "",
        )
        .group_by(Restaurant.cuisine)
        .order_by(count.desc(), Restaurant.cuisine)
        .limit(limit)
    )
    return [(cuisine, total) for cuisine, total in await session.execute(stmt)]


async def owned_restaurant(session: AsyncSession, user: Identity, restaurant_id: int) -> Restaurant:
    """Return the restaurant if the user may manage it, else raise.

    404 if it doesn't exist; 403 if it exists but the user is neither the owner
    nor an admin.
    """
    restaurant = await get_restaurant(session, restaurant_id)
    if restaurant.owner_id != user.user_id and user.role != "admin":
        raise ForbiddenException("You do not manage this restaurant")
    return restaurant


async def update_restaurant(
    session: AsyncSession, restaurant_id: int, user: Identity, data: RestaurantUpdate
) -> Restaurant:
    restaurant = await owned_restaurant(session, user, restaurant_id)
    payload = data.model_dump(exclude_unset=True)
    # Hours live in their own table — they must not be setattr'd onto Restaurant.
    schedule = payload.pop("opening_hours", None)
    for field, value in payload.items():
        setattr(restaurant, field, value)
    if schedule is not None:
        await replace_opening_hours(
            session,
            restaurant.id,
            [OpeningHourDay.model_validate(row) for row in schedule],
        )
    publish_restaurant(session, restaurant)
    await session.commit()
    await session.refresh(restaurant)
    return restaurant


async def list_cities(session: AsyncSession) -> list[str]:
    """Cities with at least one approved restaurant, sorted.

    Approved only: this fills the customer city picker, and offering a city
    whose only venue is unvetted sends them to an empty result page.
    """
    result = await session.scalars(
        select(Restaurant.city)
        .distinct()
        .order_by(Restaurant.city)
        .where(Restaurant.city.isnot(None), Restaurant.approval_status == APPROVED)
    )
    return sorted(list(set(result.all())))


def publish_restaurant(session: AsyncSession, restaurant: Restaurant) -> None:
    """Announce a restaurant to the services that keep a copy of it.

    The orders service needs the owner (to decide who may accept an order) and
    the name (to label a kitchen ticket). Both were joins; both would now be a
    synchronous call on the owner dashboard's busiest read.

    Nothing sensitive travels: an owner id, a name, and whether it is taking
    orders. The menu, the address and the phone number stay here, with the
    service that has a reason to hold them.

    ``approval_status`` rides along because a consumer deciding whether to act on
    a restaurant needs it — a rejected venue is not one the orders service should
    accept a ticket for. It is a status, not a detail about anyone, so it does
    not widen what this topic discloses.
    """
    outbox.record_event(
        session, "restaurant-events", str(restaurant.id),
        {
            "restaurant_id": restaurant.id,
            "owner_id": restaurant.owner_id,
            "name": restaurant.name,
            "is_open": restaurant.is_open,
            "approval_status": restaurant.approval_status,
        },
    )

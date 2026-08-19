"""Opening-hours schedule checks.

Complements the owner's manual ``is_open`` switch rather than replacing it:

- no schedule rows → behaviour is unchanged (``is_open`` alone decides)
- schedule present → the kitchen must be marked open *and* the clock must fall
  inside today's window

Times are local to ``settings.local_timezone``. Overnight windows (e.g. 22:00–
02:00) are supported: the closing half after midnight still belongs to the day
the kitchen opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, exists, or_, select

from app.config import settings
from app.models import OpeningHour, Restaurant


@dataclass(frozen=True)
class ScheduleStatus:
    """All clock-derived facts needed by API responses and checkout."""

    accepting_orders: bool
    local_day_of_week: int
    current_closes_at: time | None = None
    open_24_hours: bool = False
    next_opens_at: time | None = None
    next_opens_day: int | None = None


def local_now(now: datetime | None = None) -> datetime:
    """Current time in the platform's restaurant-local timezone.

    Aware datetimes are converted; naive ones are treated as already local so
    tests can pass a fixed clock without inventing a zone.
    """
    tz = _tz()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.local_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def parse_hhmm(value: str | None) -> time | None:
    """Parse ``HH:MM`` (24-hour). Empty / None → None."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    hour_s, _, minute_s = text.partition(":")
    hour, minute = int(hour_s), int(minute_s)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be HH:MM")
    return time(hour, minute)


def format_hhmm(value: time | None) -> str | None:
    if value is None:
        return None
    return f"{value.hour:02d}:{value.minute:02d}"


def schedule_status(
    is_open: bool, rows, now: datetime | None = None
) -> ScheduleStatus:
    """Evaluate the manual switch and weekly schedule once.

    This is the source of truth for checkout and all response timing metadata.
    Empty hours preserve the legacy manual-switch-only behaviour.
    """
    local = local_now(now)
    day = local.weekday()
    now_t = local.time().replace(second=0, microsecond=0)
    if not is_open:
        next_day, next_time = _next_open(rows, day, now_t)
        return ScheduleStatus(
            accepting_orders=False,
            local_day_of_week=day,
            next_opens_at=next_time,
            next_opens_day=next_day,
        )
    if not rows:
        return ScheduleStatus(accepting_orders=True, local_day_of_week=day)

    by_day = {int(r.day_of_week): r for r in rows}

    today = by_day.get(day)
    if today is not None and not today.is_closed and today.opens_at and today.closes_at:
        if today.opens_at == today.closes_at:
            return ScheduleStatus(
                accepting_orders=True,
                local_day_of_week=day,
                open_24_hours=True,
            )
        if (
            today.opens_at < today.closes_at
            and today.opens_at <= now_t < today.closes_at
        ) or (today.opens_at > today.closes_at and now_t >= today.opens_at):
            return ScheduleStatus(
                accepting_orders=True,
                local_day_of_week=day,
                current_closes_at=today.closes_at,
            )

    # Overnight carry from yesterday: e.g. Monday 22:00–02:00 still covers
    # Tuesday 01:00, and that window is stored on Monday.
    yesterday = by_day.get((day - 1) % 7)
    if (
        yesterday is not None
        and not yesterday.is_closed
        and yesterday.opens_at
        and yesterday.closes_at
        and yesterday.opens_at > yesterday.closes_at
        and now_t < yesterday.closes_at
    ):
        return ScheduleStatus(
            accepting_orders=True,
            local_day_of_week=day,
            current_closes_at=yesterday.closes_at,
        )

    next_day, next_time = _next_open(rows, day, now_t)
    return ScheduleStatus(
        accepting_orders=False,
        local_day_of_week=day,
        next_opens_at=next_time,
        next_opens_day=next_day,
    )


def _next_open(rows, day: int, now_t: time) -> tuple[int | None, time | None]:
    """Next scheduled opening within one week."""
    by_day = {int(row.day_of_week): row for row in rows}
    for ahead in range(7):
        candidate_day = (day + ahead) % 7
        row = by_day.get(candidate_day)
        if row is None or row.is_closed or row.opens_at is None:
            continue
        if ahead == 0 and row.opens_at <= now_t:
            continue
        return candidate_day, row.opens_at
    return None, None


def within_schedule_clause(now: datetime | None = None):
    """SQL equivalent of ``is_within_schedule`` for restaurant discovery.

    Checkout evaluates loaded rows in Python; browse must filter in PostgreSQL
    before paging. Keeping both representations in this domain module prevents
    Discovery from owning a second copy of the opening-hours policy.
    """
    local = local_now(now)
    day = local.weekday()
    previous_day = (day - 1) % 7
    now_t = local.time().replace(second=0, microsecond=0)

    no_schedule = ~exists(
        select(OpeningHour.id).where(OpeningHour.restaurant_id == Restaurant.id)
    )
    same_day = exists(
        select(OpeningHour.id).where(
            OpeningHour.restaurant_id == Restaurant.id,
            OpeningHour.day_of_week == day,
            OpeningHour.is_closed.is_(False),
            OpeningHour.opens_at.is_not(None),
            OpeningHour.closes_at.is_not(None),
            or_(
                OpeningHour.opens_at == OpeningHour.closes_at,
                and_(
                    OpeningHour.opens_at < OpeningHour.closes_at,
                    OpeningHour.opens_at <= now_t,
                    OpeningHour.closes_at > now_t,
                ),
                and_(
                    OpeningHour.opens_at > OpeningHour.closes_at,
                    OpeningHour.opens_at <= now_t,
                ),
            ),
        )
    )
    from_yesterday = exists(
        select(OpeningHour.id).where(
            OpeningHour.restaurant_id == Restaurant.id,
            OpeningHour.day_of_week == previous_day,
            OpeningHour.is_closed.is_(False),
            OpeningHour.opens_at.is_not(None),
            OpeningHour.closes_at.is_not(None),
            OpeningHour.opens_at > OpeningHour.closes_at,
            OpeningHour.closes_at > now_t,
        )
    )
    return or_(no_schedule, same_day, from_yesterday)

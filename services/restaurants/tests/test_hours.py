"""Unit tests for opening-hours schedule maths."""

from datetime import datetime, time
from types import SimpleNamespace

from app.hours import schedule_status


def _row(day, opens="09:00", closes="17:00", closed=False):
    def _t(s):
        h, m = s.split(":")
        return time(int(h), int(m))

    return SimpleNamespace(
        day_of_week=day,
        opens_at=None if closed else _t(opens),
        closes_at=None if closed else _t(closes),
        is_closed=closed,
    )


def test_empty_schedule_never_blocks():
    assert schedule_status(True, []).accepting_orders is True
    assert schedule_status(False, []).accepting_orders is False


def test_same_day_window():
    # Wednesday = 2
    rows = [_row(2, "10:00", "14:00")]
    assert schedule_status(True, rows, datetime(2026, 8, 19, 12, 0)).accepting_orders
    assert not schedule_status(True, rows, datetime(2026, 8, 19, 9, 59)).accepting_orders
    assert not schedule_status(True, rows, datetime(2026, 8, 19, 14, 0)).accepting_orders


def test_closed_day_blocks():
    rows = [_row(2, closed=True)]
    assert not schedule_status(True, rows, datetime(2026, 8, 19, 12, 0)).accepting_orders


def test_overnight_window_spans_midnight():
    # Tuesday night 22:00–02:00 still covers Wednesday 01:00.
    rows = [_row(1, "22:00", "02:00")]  # Tuesday
    assert schedule_status(True, rows, datetime(2026, 8, 18, 23, 0)).accepting_orders
    assert schedule_status(True, rows, datetime(2026, 8, 19, 1, 0)).accepting_orders
    assert not schedule_status(True, rows, datetime(2026, 8, 19, 3, 0)).accepting_orders


def test_manual_switch_still_wins():
    rows = [_row(2, "00:00", "23:59")]
    assert not schedule_status(False, rows, datetime(2026, 8, 19, 12, 0)).accepting_orders


def test_status_carries_current_close_and_next_open():
    rows = [_row(2, "10:00", "14:00"), _row(3, "09:00", "17:00")]
    open_now = schedule_status(True, rows, datetime(2026, 8, 19, 12, 0))
    assert open_now.accepting_orders is True
    assert open_now.current_closes_at == time(14, 0)

    closed_now = schedule_status(True, rows, datetime(2026, 8, 19, 15, 0))
    assert closed_now.accepting_orders is False
    assert closed_now.next_opens_day == 3
    assert closed_now.next_opens_at == time(9, 0)


def test_future_overnight_window_does_not_open_early():
    rows = [_row(1, "22:00", "02:00")]
    assert not schedule_status(True, rows, datetime(2026, 8, 18, 1, 0)).accepting_orders

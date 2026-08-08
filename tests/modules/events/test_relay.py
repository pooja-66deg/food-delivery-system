"""The background loop that drains the outbox.

The batch mechanics live in test_outbox.py; what matters here is the loop's
survival and pacing, because those are what decide whether events keep flowing
when something goes wrong.
"""
import asyncio

import pytest

from src.adapters import kafka
from src.config import settings
from src.modules.events import relay


@pytest.fixture(autouse=True)
def _fast_relay(monkeypatch):
    """Real intervals would make every test in this file a sleep."""
    monkeypatch.setattr(settings, "outbox_relay_enabled", True)
    monkeypatch.setattr(settings, "outbox_relay_interval_seconds", 0.01)
    monkeypatch.setattr(settings, "outbox_relay_batch_size", 2)
    monkeypatch.setattr(kafka, "is_configured", lambda: True)
    yield


async def test_loop_survives_a_failing_batch(monkeypatch):
    """One bad batch must not end the loop — a dead relay grows a silent backlog."""
    calls = []

    async def _once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("broker down")
        raise asyncio.CancelledError  # stand-in for shutdown, to end the test

    monkeypatch.setattr(relay, "relay_once", _once)

    with pytest.raises(asyncio.CancelledError):
        await relay.run_relay()

    assert len(calls) == 2, "loop stopped after the failure instead of retrying"


async def test_full_batch_drains_without_sleeping(monkeypatch):
    """A backlog must drain at the broker's pace, not one batch per tick.

    The interval is set to a minute here: if the loop slept between full batches
    this would time out rather than fail an assertion.
    """
    monkeypatch.setattr(settings, "outbox_relay_interval_seconds", 60.0)
    calls = []

    async def _once():
        calls.append(1)
        if len(calls) >= 3:
            raise asyncio.CancelledError
        return settings.outbox_relay_batch_size  # a full batch — more waiting

    monkeypatch.setattr(relay, "relay_once", _once)

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(relay.run_relay(), timeout=5)

    assert len(calls) == 3


async def test_partial_batch_waits_for_the_next_tick(monkeypatch):
    """Nothing left to drain means back off, rather than spin on an empty table."""
    monkeypatch.setattr(settings, "outbox_relay_interval_seconds", 30.0)

    async def _once():
        return 0  # queue empty

    monkeypatch.setattr(relay, "relay_once", _once)

    task = asyncio.create_task(relay.run_relay())
    await asyncio.sleep(0.05)
    assert not task.done(), "loop exited instead of waiting"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_not_started_when_kafka_is_disabled(monkeypatch):
    """Otherwise every row's attempts counter climbs forever on a dev machine."""
    monkeypatch.setattr(kafka, "is_configured", lambda: False)
    relay.start_relay()
    assert relay._task is None
    await relay.stop_relay()


async def test_not_started_when_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "outbox_relay_enabled", False)
    relay.start_relay()
    assert relay._task is None
    await relay.stop_relay()


async def test_start_then_stop_is_clean(monkeypatch):
    async def _once():
        return 0

    monkeypatch.setattr(relay, "relay_once", _once)

    relay.start_relay()
    assert relay._task is not None
    await asyncio.sleep(0.02)

    await relay.stop_relay()
    assert relay._task is None


async def test_stop_without_start_is_a_no_op():
    await relay.stop_relay()  # must not raise

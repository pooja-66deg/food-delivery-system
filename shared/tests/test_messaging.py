"""The delivery semantics every service now inherits.

This module replaced six hand-written poll loops, so the rules it encodes are the
rules everywhere. Three of them decide whether events are lost, repeated, or
stuck, and none of them is obvious from reading the code once:

- a handler that succeeds acknowledges the message;
- a handler that raises does **not**, so it is redelivered;
- a payload that cannot be parsed at all *is* acknowledged, because
  redelivering it forever would stop every later message on that topic.
"""

import asyncio
import json

import pytest

from shared.messaging import EventConsumer, publisher_for, unwrap


def _consumer(handlers, **kwargs) -> EventConsumer:
    return EventConsumer(
        transport="kafka", topics=["order-events"], group="test",
        handlers=handlers, session_factory=_null_session, **kwargs,
    )


class _NullSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _null_session():
    return _NullSession()


def test_a_flat_payload_passes_through():
    assert unwrap({"order_id": 1}) == {"order_id": 1}


def test_an_enveloped_payload_is_unwrapped():
    """Publishers may wrap as {id, event_type, data}; accepting both keeps an
    envelope change from silently freezing a consumer."""
    assert unwrap({"id": "e1", "event_type": "x", "data": {"order_id": 1}}) == {"order_id": 1}


def test_a_successful_handler_acknowledges():
    seen = []

    async def handler(session, payload):
        seen.append(payload)

    loop = asyncio.new_event_loop()
    thread_loop = _run_loop(loop)
    try:
        consumer = _consumer({"order-events": handler})
        assert consumer._handle(loop, "order-events", json.dumps({"order_id": 1}).encode())
        assert seen == [{"order_id": 1}]
    finally:
        _stop_loop(loop, thread_loop)


def test_a_raising_handler_does_not_acknowledge():
    """The message comes back. A lost payment event is an order that never
    leaves the kitchen, so repeating beats dropping."""
    async def handler(session, payload):
        raise RuntimeError("boom")

    loop = asyncio.new_event_loop()
    thread_loop = _run_loop(loop)
    try:
        consumer = _consumer({"order-events": handler})
        assert not consumer._handle(loop, "order-events", json.dumps({"order_id": 1}).encode())
    finally:
        _stop_loop(loop, thread_loop)


def test_an_unparseable_payload_is_acknowledged_and_skipped():
    """The one case where dropping is right: it will never parse, and holding the
    offset would stop the topic for every later message."""
    calls = []

    async def handler(session, payload):
        calls.append(payload)

    loop = asyncio.new_event_loop()
    thread_loop = _run_loop(loop)
    try:
        consumer = _consumer({"order-events": handler})
        assert consumer._handle(loop, "order-events", b"not json at all")
        assert calls == [], "a malformed message reached the handler"
    finally:
        _stop_loop(loop, thread_loop)


def test_a_topic_with_no_handler_is_acknowledged():
    """Subscribing to something nobody handles is a config mistake, not a reason
    to stall the subscription."""
    loop = asyncio.new_event_loop()
    thread_loop = _run_loop(loop)
    try:
        consumer = _consumer({})
        assert consumer._handle(loop, "order-events", json.dumps({"order_id": 1}).encode())
    finally:
        _stop_loop(loop, thread_loop)


def test_pubsub_without_a_project_id_fails_loudly():
    """A deploy that silently picked the wrong transport would look healthy and
    publish into the void, so the mistake is made at startup instead."""
    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        publisher_for(transport="pubsub", kafka_servers="kafka:9092", project_id=None)


# -- a real loop on a background thread, so run_coroutine_threadsafe works ----


def _run_loop(loop):
    import threading

    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return thread


def _stop_loop(loop, thread):
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()

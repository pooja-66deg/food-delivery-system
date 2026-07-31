"""Transactional outbox: record + relay."""
import json

import pytest

from src.modules.events import outbox
from src.modules.events.models import OutboxEvent
from sqlalchemy import select


@pytest.mark.asyncio
async def test_record_event_persists_unpublished(db_session):
    outbox.record_event(db_session, "order-events", "42", {"order_id": 42, "status": "CREATED"})
    await db_session.commit()
    rows = list(await db_session.scalars(select(OutboxEvent)))
    assert len(rows) == 1
    assert rows[0].published_at is None
    assert json.loads(rows[0].payload)["order_id"] == 42


@pytest.mark.asyncio
async def test_relay_publishes_and_stamps(db_session, monkeypatch):
    sent = []

    async def _fake_send(topic, key, value):
        sent.append((topic, key, value))

    monkeypatch.setattr(outbox, "send_event", _fake_send)

    outbox.record_event(db_session, "order-events", "7", {"order_id": 7})
    await db_session.commit()

    published = await outbox.relay_outbox(db_session)
    assert published == 1
    assert sent == [("order-events", "7", {"order_id": 7})]
    row = (await db_session.scalars(select(OutboxEvent))).one()
    assert row.published_at is not None


@pytest.mark.asyncio
async def test_relay_leaves_unpublished_on_failure(db_session, monkeypatch):
    async def _boom(topic, key, value):
        raise RuntimeError("broker down")

    monkeypatch.setattr(outbox, "send_event", _boom)

    outbox.record_event(db_session, "order-events", "9", {"order_id": 9})
    await db_session.commit()

    published = await outbox.relay_outbox(db_session)
    assert published == 0
    row = (await db_session.scalars(select(OutboxEvent))).one()
    assert row.published_at is None
    assert row.attempts == 1

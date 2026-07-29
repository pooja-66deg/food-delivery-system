"""Outbox helpers: record events transactionally and relay them to Kafka."""
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.kafka import send_event
from src.modules.events.models import OutboxEvent


def record_event(session: AsyncSession, topic: str, key: str | None, payload: dict) -> None:
    """Append an outbox row to the current transaction (caller commits)."""
    session.add(OutboxEvent(topic=topic, key=key, payload=json.dumps(payload)))


async def relay_outbox(session: AsyncSession, batch_size: int = 100) -> int:
    """Publish unpublished outbox rows to Kafka and stamp them. Returns the
    number published. Rows that fail to publish are left for a later run (their
    ``attempts`` counter is bumped)."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(batch_size)
    )
    rows = list(await session.scalars(stmt))
    published = 0
    for row in rows:
        try:
            await send_event(row.topic, row.key, json.loads(row.payload))
            row.published_at = datetime.now(timezone.utc)
            published += 1
        except Exception:  # noqa: BLE001 — leave for retry, don't abort the batch
            row.attempts += 1
    await session.commit()
    return published

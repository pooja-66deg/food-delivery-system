"""This service's outbox, bound to its own table.

A thin binding rather than an implementation: the mechanics live in
``shared/outbox.py`` so all six services drain their tables the same way, and
only the model differs.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from shared import outbox as shared_outbox


def record_event(
    session: AsyncSession, topic: str, key: Optional[str], payload: dict
) -> None:
    """Append an event to the caller's transaction. The caller commits."""
    shared_outbox.record_event(session, OutboxEvent, topic, key, payload)

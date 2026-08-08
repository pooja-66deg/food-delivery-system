"""The transactional outbox, once, for every service.

A service writes its event in the same transaction as the state change that
caused it. Both commit or neither does, which is the one guarantee publishing
directly to Kafka cannot give: without it a broker blip either loses an event
whose state change succeeded, or fails a write whose event was already sent.

A relay then drains the table. It runs inside each service rather than as a
separate worker, so a running service is enough to guarantee delivery — one less
thing that can be forgotten in a deploy.

The model is passed in rather than defined here because each service has its own
``Base`` and its own ``outbox_events`` table. Same code, six tables, no shared
database between them.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: ``(topic, key, value) -> None``, raising if the publish failed. Satisfied by
#: anything in ``shared.messaging`` — Kafka locally, Pub/Sub in production.
Sender = Callable[[str, Optional[str], dict], Awaitable[None]]


def record_event(session: AsyncSession, model, topic: str, key: Optional[str], payload: dict) -> None:
    """Append an outbox row to the caller's transaction. The caller commits."""
    session.add(model(topic=topic, key=key, payload=json.dumps(payload, default=str)))


async def drain(session: AsyncSession, model, send: Sender, batch_size: int = 100) -> int:
    """Publish one batch of unpublished rows. Returns how many went out.

    A row that fails to publish is left unpublished and its ``attempts`` counter
    bumped, so one bad event cannot block the rest of the batch — and cannot be
    silently dropped either.
    """
    stmt = (
        select(model)
        .where(model.published_at.is_(None))
        .order_by(model.id)
        .limit(batch_size)
    )
    # With more than one replica each runs its own relay, and without this they
    # all read the same rows and publish every event N times. SKIP LOCKED hands
    # each relay a disjoint batch instead of making them queue. SQLite (tests)
    # has neither, and needs neither — there is only ever one writer.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    rows = list(await session.scalars(stmt))
    published = 0
    for row in rows:
        try:
            await send(row.topic, row.key, json.loads(row.payload))
            row.published_at = datetime.now(timezone.utc)
            published += 1
        except Exception:  # noqa: BLE001 — leave for retry, don't abort the batch
            row.attempts += 1
    await session.commit()
    return published


class OutboxRelay:
    """Drains one service's outbox until stopped."""

    def __init__(
        self,
        session_factory,
        model,
        send: Sender,
        *,
        interval_seconds: float = 1.0,
        batch_size: int = 100,
    ):
        self._session_factory = session_factory
        self._model = model
        self._send = send
        self._interval = interval_seconds
        self._batch_size = batch_size
        self._task: Optional[asyncio.Task] = None

    async def relay_once(self) -> int:
        """One pass, in its own session.

        Its own, deliberately: the relay must not share a transaction with a
        request handler, or a slow broker would hold that request's rows locked.
        """
        async with self._session_factory() as session:
            return await drain(session, self._model, self._send, self._batch_size)

    async def run(self) -> None:
        """Drain until cancelled.

        Swallows everything but cancellation. A relay that dies on its first bad
        batch is worse than one that never started, because writes keep
        succeeding and the backlog grows behind a process that looks healthy.
        """
        logger.info("Outbox relay started (every %ss, batches of %s)", self._interval, self._batch_size)
        while True:
            try:
                published = await self.relay_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — see docstring
                logger.exception("Outbox relay batch failed; retrying next tick")
                published = 0

            # A full batch means more is probably waiting. Going straight round
            # again lets a backlog drain at the broker's pace rather than one
            # batch per tick, which after an outage would take hours.
            if published >= self._batch_size:
                continue
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="outbox-relay")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            logger.info("Outbox relay stopped")


def relay_for(session_factory, model, publisher, **kwargs) -> "OutboxRelay":
    """An ``OutboxRelay`` that drains through ``publisher``.

    A one-liner, but it is the seam that keeps the transport out of every
    service's lifespan: they build a publisher from their settings and hand it
    over, and none of them mentions Kafka or Pub/Sub by name.
    """
    return OutboxRelay(
        session_factory, model, lambda topic, key, value: publisher.publish(topic, key, value),
        **kwargs,
    )

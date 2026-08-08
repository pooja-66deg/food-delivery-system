"""Background relay that drains the outbox to Kafka.

``record_event`` writes an event row in the same transaction as the state change
that caused it, which is what makes the two impossible to disagree. Nothing
publishes those rows, though, until something drains them — that is this module.

It runs in-process as a lifespan task rather than as a separate cron/worker so a
running API is enough to guarantee delivery. When the platform splits into
services each one starts its own relay over its own outbox table; the loop here
is what they inherit.
"""

import asyncio
import logging

from src.adapters import kafka
from src.adapters.database import async_session
from src.config import settings
from src.modules.events.outbox import relay_outbox

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def relay_once() -> int:
    """Drain one batch. Returns how many events were published.

    Opens its own session: the relay must not share a transaction with a request
    handler, or a slow broker would hold that request's rows locked.
    """
    async with async_session() as session:
        return await relay_outbox(session, batch_size=settings.outbox_relay_batch_size)


async def run_relay() -> None:
    """Drain the outbox until cancelled.

    Deliberately swallows every exception except cancellation. A relay that dies
    on its first bad batch is worse than one that never started, because writes
    keep succeeding and the backlog grows silently behind a process that looks
    healthy. Failures are logged and retried on the next tick; per-row failures
    are already counted in ``OutboxEvent.attempts``.
    """
    logger.info(
        "Outbox relay started (every %ss, batches of %s)",
        settings.outbox_relay_interval_seconds,
        settings.outbox_relay_batch_size,
    )
    while True:
        try:
            published = await relay_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — see docstring: the loop must survive
            logger.exception("Outbox relay batch failed; retrying next tick")
            published = 0

        # A full batch means there is probably more waiting. Going straight round
        # again lets a backlog drain at the broker's pace instead of one batch
        # per tick, which after an outage would take hours to catch up.
        if published >= settings.outbox_relay_batch_size:
            continue
        await asyncio.sleep(settings.outbox_relay_interval_seconds)


def start_relay() -> None:
    """Start the relay as a background task, if it should run at all."""
    global _task
    if not settings.outbox_relay_enabled:
        logger.info("Outbox relay disabled (OUTBOX_RELAY_ENABLED=false); events will not publish.")
        return
    # A configured-but-unreachable broker is worth retrying — that is the point
    # of an outbox. A deliberately disabled one is not: the relay would just bump
    # `attempts` on every row forever, turning a local dev setup into a
    # permanently "failing" queue.
    if not kafka.is_configured():
        logger.info("Outbox relay not started: Kafka is disabled.")
        return
    _task = asyncio.create_task(run_relay(), name="outbox-relay")


async def stop_relay() -> None:
    """Cancel the relay and wait for it to unwind."""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    finally:
        _task = None
        logger.info("Outbox relay stopped")

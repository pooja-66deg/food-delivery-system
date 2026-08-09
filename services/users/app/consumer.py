"""Consumer: lets an approved restaurant owner in.

The only thing this service listens for, and it exists because approval is
decided somewhere else. A restaurant applicant registers inactive; the operator
who reviews their venue does so in the restaurants service, against a row in the
restaurants database. Something has to carry that decision back to the account,
and an event is the option that does not make approving a venue depend on this
service being up — the decision is committed there either way, and the account
catches up when the message is delivered.

The alternative, a synchronous call from restaurants to users inside the
approval request, would mean an operator clicking Approve gets a 500 during a
users deploy, with the venue approved and the owner still locked out. That split
state is exactly what the outbox exists to avoid.

Runs in a worker thread, like every other consumer here: kafka-python is a
blocking client and its poll loop would otherwise stall the event loop serving
HTTP.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.config import settings
from app.db import async_session

from shared.messaging import EventConsumer

logger = logging.getLogger(__name__)

_consumer: EventConsumer | None = None


async def _apply_restaurant_event(session: AsyncSession, payload: dict) -> None:
    """Grant or record access from a restaurant's current approval status.

    ``restaurant-events`` is published on every change to a restaurant, not only
    on approval — an owner renaming their venue or closing the kitchen produces
    one too. That is fine and deliberately not filtered here: the handler is
    idempotent, so an event that carries an unchanged status does nothing, and
    reacting to state rather than to a "was approved just now" signal means a
    decision cannot be missed because its one event went astray.
    """
    owner_id = payload.get("owner_id")
    status = payload.get("approval_status")
    if owner_id is None or status is None:
        # Not something this service can act on. Returning rather than raising
        # acknowledges it: a payload we will never understand would otherwise be
        # redelivered forever and block the topic behind it.
        return

    changed = await service.apply_restaurant_decision(session, owner_id, status)
    if changed:
        logger.info(
            "[users] owner %s approval status is now %s", owner_id, status
        )


_HANDLERS = {
    "restaurant-events": _apply_restaurant_event,
}


def start_consumer(loop) -> None:
    """Start consuming. Topics and handlers are the only part that is ours —
    the loop, the threading and the ack rules live in ``shared.messaging``."""
    global _consumer
    _consumer = EventConsumer(
        transport=settings.messaging_transport,
        topics=settings.topics,
        group=settings.kafka_group_id,
        handlers=_HANDLERS,
        session_factory=async_session,
        kafka_servers=settings.kafka_bootstrap_servers,
        project_id=settings.google_cloud_project,
    )
    _consumer.start(loop)


def stop_consumer() -> None:
    global _consumer
    if _consumer is not None:
        _consumer.stop()
        _consumer = None

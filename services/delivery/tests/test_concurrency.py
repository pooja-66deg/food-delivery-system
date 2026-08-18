"""The driver-action row locks, against a database that actually has them.

Same reasoning as the orders service's file of this name: the rest of the suite
runs on in-memory SQLite, which serialises every write and therefore cannot
produce the interleaving these guard against. Skipped unless a PostgreSQL URL is
present; CI has one.

    DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery \\
      ./services/test.sh delivery

The asymmetry these were written for: ``accept_assignment`` took a row lock and
``reject_assignment`` did not. Under MVCC a plain SELECT does not wait on a
locked row — it reads the last committed version — so a reject overlapping an
accept saw the delivery still ASSIGNED, passed its own status check, and
unassigned a delivery the driver had just been told was theirs. ``pickup`` and
``deliver`` had the same shape.
"""

import asyncio
import os

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import service as delivery_service
from app.models import Base, Delivery, DeliveryStatus, Driver, OutboxEvent


def _postgres_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        return None
    base, _, _ = url.rpartition("/")
    return f"{base}/delivery_db".replace("postgresql://", "postgresql+asyncpg://")


pytestmark = pytest.mark.skipif(
    _postgres_url() is None,
    reason="needs PostgreSQL: SQLite has one writer, so no interleaving is possible",
)

DRIVER_ID = 42


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(_postgres_url(), poolclass=None)
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.drop_all)
        except Exception:
            pass  # Ignore errors if tables don't exist
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.drop_all)
        except Exception:
            pass  # Ignore errors during cleanup
    await engine.dispose()


async def _truncate_everything(factory) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with factory() as cleanup:
        await cleanup.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        await cleanup.commit()


@pytest_asyncio.fixture
async def sessions(pg_engine):
    """Two sessions, so there are two connections to contend."""
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    await _truncate_everything(factory)
    async with factory() as a, factory() as b:
        yield a, b
    await _truncate_everything(factory)


async def _seed(session: AsyncSession, status: str) -> int:
    session.add(Driver(id=DRIVER_ID, first_name="Dee"))
    delivery = Delivery(order_id=1, driver_id=DRIVER_ID, status=status)
    session.add(delivery)
    await session.commit()
    return delivery.order_id


async def _call(fn, session, order_id):
    """One driver action. Returns the exception rather than raising."""
    try:
        return await fn(session, DRIVER_ID, order_id)
    except Exception as exc:  # noqa: BLE001 — the outcome under test
        return exc


def _split(outcomes):
    won = [o for o in outcomes if not isinstance(o, Exception)]
    refused = [o for o in outcomes if isinstance(o, HTTPException)]
    return won, refused


def _gate_commit(session) -> asyncio.Event:
    """Park this session just before it commits, until the returned event is set.

    ``asyncio.gather`` on two calls is not enough to test a lock, and this file
    originally made that mistake: the first call ran to completion — commit
    included — before the second read anything, so the second was refused by an
    already-updated row and the test passed whether or not the lock existed. It
    proved the two calls did not overlap, which is the opposite of the point.

    Holding the first transaction open at the commit boundary makes the overlap
    deterministic. The row is written and locked but not yet visible, which is
    exactly the window a second request has to arrive in for any of this to
    matter.
    """
    gate = asyncio.Event()
    real_commit = session.commit

    async def commit_when_released():
        await gate.wait()
        await real_commit()

    session.commit = commit_when_released
    return gate


async def _assert_second_call_blocks(first, second, gate):
    """The second call must not get anywhere while the first holds the row.

    With ``FOR UPDATE`` it blocks in the SELECT. Without it, a plain SELECT reads
    the last committed version rather than waiting, so it sails past its status
    check on a row it cannot see has already changed — and finishes.
    """
    await asyncio.sleep(0.4)
    assert not second.done(), (
        "the second call completed while the first still held the row: "
        "its SELECT did not wait, so it acted on a stale status"
    )

    gate.set()
    return await asyncio.wait_for(first, timeout=5), await asyncio.wait_for(second, timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action, start_status",
    [
        ("reject_assignment", DeliveryStatus.ASSIGNED.value),
        ("pickup", DeliveryStatus.ACCEPTED.value),
        ("deliver", DeliveryStatus.PICKED_UP.value),
    ],
)
async def test_a_second_driver_action_waits_for_the_first(sessions, action, start_status):
    """The three that had no lock, each with the state it acts from.

    All three shared one shape: read the delivery, check its status, write. With
    the read unlocked, two overlapping requests both pass the check against the
    same stale row — a doubled pickup advances the order to OUT_FOR_DELIVERY
    twice, a doubled deliver emits two DELIVERED events and so two settle
    commands, and a doubled reject runs driver selection twice and can offer the
    same order to the next driver twice.
    """
    a, b = sessions
    order_id = await _seed(a, start_status)
    fn = getattr(delivery_service, action)

    gate = _gate_commit(a)
    first = asyncio.create_task(_call(fn, a, order_id))
    await asyncio.sleep(0.2)                       # a is parked holding the row
    second = asyncio.create_task(_call(fn, b, order_id))

    outcomes = await _assert_second_call_blocks(first, second, gate)
    won, refused = _split(outcomes)

    assert len(won) == 1, f"expected one {action} to win, got {outcomes}"
    assert len(refused) == 1, f"expected the loser to be refused, got {outcomes}"


@pytest.mark.asyncio
async def test_a_doubled_reject_announces_one_status_change(sessions):
    """Two reject events for one delivery is a sequence that never happened."""
    a, b = sessions
    order_id = await _seed(a, DeliveryStatus.ASSIGNED.value)

    gate = _gate_commit(a)
    first = asyncio.create_task(_call(delivery_service.reject_assignment, a, order_id))
    await asyncio.sleep(0.2)
    second = asyncio.create_task(_call(delivery_service.reject_assignment, b, order_id))
    await _assert_second_call_blocks(first, second, gate)

    b.expire_all()
    events = await b.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.topic == "delivery-events")
    )
    assert events == 1, f"expected one delivery event, found {events}"


@pytest.mark.asyncio
async def test_a_reject_cannot_overwrite_an_acceptance_it_never_saw(sessions):
    """The original asymmetry: accept held the lock, reject did not.

    A reject overlapping an accept read around it, saw ASSIGNED, and unassigned a
    delivery the driver had just been given — so that driver's app showed an
    order that had been offered to somebody else.
    """
    a, b = sessions
    order_id = await _seed(a, DeliveryStatus.ASSIGNED.value)

    gate = _gate_commit(a)
    accepting = asyncio.create_task(_call(delivery_service.accept_assignment, a, order_id))
    await asyncio.sleep(0.2)
    rejecting = asyncio.create_task(_call(delivery_service.reject_assignment, b, order_id))

    await _assert_second_call_blocks(accepting, rejecting, gate)

    b.expire_all()
    final = await b.scalar(select(Delivery).where(Delivery.order_id == order_id))
    accepted_with_no_driver = (
        final.status == DeliveryStatus.ACCEPTED.value and final.driver_id is None
    )
    assert not accepted_with_no_driver, (
        f"delivery is {final.status} with driver_id={final.driver_id}"
    )


@pytest.mark.asyncio
async def test_the_lock_serialises_rather_than_failing_fast(sessions):
    """FOR UPDATE, not NOWAIT: the loser waits its turn rather than erroring."""
    a, b = sessions
    order_id = await _seed(a, DeliveryStatus.ASSIGNED.value)

    await delivery_service._owned_active(a, DRIVER_ID, order_id, for_update=True)

    async def second_reader():
        await delivery_service._owned_active(b, DRIVER_ID, order_id, for_update=True)
        return "acquired"

    task = asyncio.create_task(second_reader())
    await asyncio.sleep(0.2)
    assert not task.done(), "second FOR UPDATE returned while the row was locked"

    await a.commit()
    assert await asyncio.wait_for(task, timeout=5) == "acquired"
    await b.commit()

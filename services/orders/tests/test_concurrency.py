"""The row locks, against a database that actually has them.

The rest of this suite runs on in-memory SQLite, which is the right default — a
service whose tests need infrastructure is a service nobody runs the tests for.
It is also why the bug these guard against survived: SQLite serialises every
write, so the interleaving simply cannot occur there, and a suite that cannot
produce a race cannot notice one missing lock.

So these skip unless a PostgreSQL URL is present. CI has one — the backend job
runs a Postgres service and already creates ``orders_db`` for the migration
round-trip — so this is covered on every push, and skipped on a laptop with
nothing running.

    DATABASE_URL=postgresql://fooduser:foodpass@localhost:5432/fooddelivery \\
      ./services/test.sh orders

What is being tested is not "does FOR UPDATE appear in the SQL" — that is a
spelling check. It is the behaviour: two overlapping requests that both read the
same order must not both act on it.
"""

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import checkout as checkout_service
from app import service as order_service
from app.models import (
    Base, Order, OrderStatus, OutboxEvent, PaymentMethod, PaymentStatus,
    RestaurantSnapshot,
)
from app.state_machine import OrderError


def _postgres_url() -> str | None:
    """The orders service's database, derived from the job's DATABASE_URL.

    CI points DATABASE_URL at the shared ``fooddelivery`` database; each service
    owns ``<service>_db`` beside it, which the migration step has already
    created. Only the final path segment differs, so it is swapped rather than
    requiring a second variable nobody would remember to set.
    """
    url = os.getenv("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        return None
    base, _, _ = url.rpartition("/")
    return f"{base}/orders_db".replace("postgresql://", "postgresql+asyncpg://")


pytestmark = pytest.mark.skipif(
    _postgres_url() is None,
    reason="needs PostgreSQL: SQLite has one writer, so no interleaving is possible",
)


@pytest_asyncio.fixture
async def pg_engine():
    try:
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
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


async def _truncate_everything(factory) -> None:
    """Empty every table, in one statement.

    ``DELETE`` per table needs foreign keys honoured in order —
    ``order_status_events`` references ``orders`` — and getting that order wrong
    leaves rows behind, which then surface as a primary-key collision in the
    *next* test's fixture rather than as a cleanup failure. TRUNCATE ... CASCADE
    has no such ordering to get wrong.
    """
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with factory() as cleanup:
        await cleanup.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        await cleanup.commit()


@pytest_asyncio.fixture
async def sessions(pg_engine):
    """Two independent sessions — two connections, as two requests would be.

    One session with two transactions would not test anything: the lock is held
    per connection, so a single connection never contends with itself.
    """
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    # Before as well as after: this database is shared with the migration
    # round-trip in CI and with whatever a previous interrupted run left behind.
    await _truncate_everything(factory)

    async with factory() as a, factory() as b:
        yield a, b

    await _truncate_everything(factory)


@pytest.fixture(autouse=True)
def no_stock_call(monkeypatch):
    """The cancel path calls the restaurants service to put stock back.

    Nothing is listening in a test run, and the real client would spend its
    timeout finding that out on every cancel. It is best-effort by design, so
    stubbing it changes nothing this file is measuring.
    """
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(checkout_service, "release_stock", _noop)


async def _seed_accepted_order(session: AsyncSession) -> int:
    """An order a restaurant has accepted, i.e. one that can still be cancelled."""
    session.add(RestaurantSnapshot(restaurant_id=1, name="Test Kitchen", owner_id=99))
    order = Order(
        customer_id=1, restaurant_id=1, address_id=1,
        status=OrderStatus.RESTAURANT_ACCEPTED.value,
        payment_method=PaymentMethod.CARD.value,
        payment_status=PaymentStatus.SUCCESS.value,
        subtotal=Decimal("200.00"), delivery_fee=Decimal("0"),
        total=Decimal("200.00"),
    )
    session.add(order)
    await session.commit()
    return order.id


_OWNER = SimpleNamespace(user_id=99, role="restaurant")


async def _cancel(session: AsyncSession, order_id: int):
    """One cancel request. Returns the exception rather than raising it.

    ``asyncio.gather`` with ``return_exceptions=True`` would do the same, but
    doing it here keeps the assertions about outcomes rather than about gather's
    result shape.
    """
    try:
        return await order_service.advance_status(
            session, _OWNER, order_id, OrderStatus.CANCELLED
        )
    except Exception as exc:  # noqa: BLE001 — the outcome under test
        return exc


def _gate_commit(session) -> asyncio.Event:
    """Park this session just before it commits, until the returned event is set.

    Two calls handed to ``asyncio.gather`` are not reliably concurrent: whether
    they overlap depends on where the event loop happens to yield, so the test
    can pass because nothing raced rather than because the lock worked. The
    delivery service's version of this file had exactly that bug — every test
    passed with the locks removed.

    Holding the first transaction open at the commit boundary removes the
    timing. The row is written and locked but not yet visible, which is precisely
    the window a second request must arrive in for any of this to matter.
    """
    gate = asyncio.Event()
    real_commit = session.commit

    async def commit_when_released():
        await gate.wait()
        await real_commit()

    session.commit = commit_when_released
    return gate


async def _assert_second_call_blocks(first, second, gate):
    """The second request must make no progress while the first holds the row.

    With ``FOR UPDATE`` it blocks in the SELECT. Without it, a plain SELECT reads
    the last committed version instead of waiting, so it validates a status it
    cannot see has already changed — and finishes.
    """
    await asyncio.sleep(0.4)
    assert not second.done(), (
        "the second cancel completed while the first still held the row: "
        "its SELECT did not wait, so the state machine judged a stale status"
    )
    gate.set()
    return await asyncio.wait_for(first, timeout=5), await asyncio.wait_for(second, timeout=5)


async def _two_overlapping_cancels(a, b, order_id):
    """Both cancels genuinely in flight at once. Returns their outcomes."""
    gate = _gate_commit(a)
    first = asyncio.create_task(_cancel(a, order_id))
    await asyncio.sleep(0.2)                    # a is parked holding the row
    second = asyncio.create_task(_cancel(b, order_id))
    return await _assert_second_call_blocks(first, second, gate)


@pytest.mark.asyncio
async def test_two_simultaneous_cancels_only_one_takes_effect(sessions):
    """Both requests read the order, both think it is cancellable, both write.

    Without FOR UPDATE the second transaction reads the pre-cancel row — under
    MVCC a plain SELECT does not wait on a locked row, it reads the last
    committed version — so the state machine validates a status that is already
    stale and lets the cancel through a second time.

    With the lock the second blocks until the first commits, re-reads CANCELLED,
    and is refused on its merits: CANCELLED has no outbound transitions.
    """
    a, b = sessions
    order_id = await _seed_accepted_order(a)

    outcomes = await _two_overlapping_cancels(a, b, order_id)
    succeeded = [o for o in outcomes if not isinstance(o, Exception)]
    refused = [o for o in outcomes if isinstance(o, OrderError)]

    assert len(succeeded) == 1, f"expected exactly one cancel to win, got {outcomes}"
    assert len(refused) == 1, f"expected the loser to be refused, got {outcomes}"


@pytest.mark.asyncio
async def test_a_doubled_cancel_does_not_request_two_refunds(sessions):
    """The consequence that costs money.

    ``advance_status`` records a ``refund`` on payment-commands inside the same
    transaction as the cancellation. Two cancels that both commit therefore
    publish two refund commands for one order. The payments service now refuses
    the second (see its test_idempotency.py), but defence in depth is the point:
    the duplicate should never be emitted at all.
    """
    a, b = sessions
    order_id = await _seed_accepted_order(a)

    await _two_overlapping_cancels(a, b, order_id)

    b.expire_all()
    refunds = await b.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(
            OutboxEvent.topic == "payment-commands",
            OutboxEvent.payload.like('%"action": "refund"%'),
        )
    )
    assert refunds == 1, f"expected one refund command, found {refunds}"


@pytest.mark.asyncio
async def test_a_doubled_cancel_emits_one_status_event(sessions):
    """Two CANCELLED events for one order is a sequence that never happened.

    Every downstream service — delivery, notifications, the admin read-model —
    consumes order-events and would each act on both.
    """
    a, b = sessions
    order_id = await _seed_accepted_order(a)

    await _two_overlapping_cancels(a, b, order_id)

    b.expire_all()
    cancelled_events = await b.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(
            OutboxEvent.topic == "order-events",
            OutboxEvent.payload.like('%"status": "CANCELLED"%'),
        )
    )
    assert cancelled_events == 1, f"expected one CANCELLED event, found {cancelled_events}"


@pytest.mark.asyncio
async def test_the_order_ends_cancelled_exactly_once(sessions):
    """Whatever else happens, the row itself must be consistent.

    This one passes with or without the lock — both cancels set the same status
    — and is kept as a consistency check rather than a race detector. The two
    above are what fail when the lock is removed.
    """
    a, b = sessions
    order_id = await _seed_accepted_order(a)

    await _two_overlapping_cancels(a, b, order_id)

    b.expire_all()
    order = await b.get(Order, order_id)
    assert order.status == OrderStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_the_lock_serialises_rather_than_failing_fast(sessions):
    """FOR UPDATE, not FOR UPDATE NOWAIT — the loser waits, it does not error.

    Worth pinning: NOWAIT or SKIP LOCKED here would turn ordinary contention
    into a 500 for a restaurant that simply tapped twice, instead of the honest
    "this order can no longer be cancelled" the state machine gives.
    """
    a, b = sessions
    order_id = await _seed_accepted_order(a)

    await order_service._locked_order(a, order_id)

    async def second_reader():
        await order_service._locked_order(b, order_id)
        return "acquired"

    task = asyncio.create_task(second_reader())
    await asyncio.sleep(0.2)
    assert not task.done(), "second FOR UPDATE returned while the row was locked"

    await a.commit()
    assert await asyncio.wait_for(task, timeout=5) == "acquired"
    await b.commit()

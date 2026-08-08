"""Money, and the two places the split changed how it moves.

The payment is created by an *event* now rather than by checkout calling in, and
the order it belongs to is read from a local snapshot rather than another
service's table. Both of those are new failure surfaces, so both are what these
tests are mostly about.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app import consumer, service
from app.models import OrderSnapshot, Payment, PaymentTxStatus


def _order_event(order_id=1, status="PAYMENT_PENDING", total="12.00", method="CARD"):
    return {
        "order_id": order_id, "customer_id": 1, "status": status,
        "total": total, "payment_method": method,
    }


async def test_an_order_event_creates_the_payment(session):
    await consumer._apply_order_event(session, _order_event())
    payment = await service.get_payment(session, 1)
    assert payment is not None
    assert Decimal(payment.amount) == Decimal("12.00")


async def test_a_cash_order_gets_a_payment_too(session):
    """The bug this test exists for.

    A COD order is authorised at creation, so checkout advances it
    PENDING -> SUCCESS and emits *one* event carrying PAYMENT_SUCCESS. Listening
    for PAYMENT_PENDING alone left every cash order with no payment row, which
    is invisible until someone reconciles the day's takings.
    """
    await consumer._apply_order_event(
        session, _order_event(status="PAYMENT_SUCCESS", method="COD")
    )
    payment = await service.get_payment(session, 1)
    assert payment is not None
    assert payment.provider == "COD"
    assert Decimal(payment.amount) == Decimal("12.00")


async def test_a_replayed_event_does_not_charge_twice(session):
    """The property that makes at-least-once delivery safe for money."""
    event = _order_event()
    await consumer._apply_order_event(session, event)
    await consumer._apply_order_event(session, event)

    payments = list(await session.scalars(select(Payment)))
    assert len(payments) == 1


async def test_an_early_status_creates_nothing(session):
    await consumer._apply_order_event(session, _order_event(status="CREATED"))
    assert await service.get_payment(session, 1) is None


async def test_a_thinner_later_event_does_not_erase_the_amount(session):
    """Only fields the event actually carries overwrite the snapshot."""
    await consumer._apply_order_event(session, _order_event())
    await consumer._apply_order_event(
        session, {"order_id": 1, "status": "RESTAURANT_ACCEPTED"}
    )
    snapshot = await session.get(OrderSnapshot, 1)
    assert Decimal(snapshot.total) == Decimal("12.00")


async def test_my_payments_joins_the_local_snapshot(session):
    """"My payments" stays a single-database read — no call to orders."""
    await consumer._apply_order_event(session, _order_event(order_id=1))
    await consumer._apply_order_event(session, {
        "order_id": 2, "customer_id": 99, "status": "PAYMENT_PENDING",
        "total": "5.00", "payment_method": "CARD",
    })

    mine = await service.list_for_customer(session, customer_id=1)
    assert [p.order_id for p in mine] == [1]


# ---- webhook --------------------------------------------------------------


@pytest.fixture
async def authorized_payment(session):
    await consumer._apply_order_event(session, _order_event())
    payment = await service.get_payment(session, 1)
    payment.provider_ref = "pi_test_123"
    payment.status = PaymentTxStatus.AUTHORIZED.value
    await session.commit()
    return payment


async def test_a_duplicate_webhook_is_recognised(session, authorized_payment):
    import fakeredis.aioredis

    from app import webhook

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    event = {
        "id": "evt_1", "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_123"}},
    }
    assert await webhook.handle_event(session, redis, event) != "duplicate"
    assert await webhook.handle_event(session, redis, event) == "duplicate"


async def test_without_redis_the_webhook_still_settles(session, authorized_payment):
    """Fail-open, and only here.

    Redis is what tells a redelivery from a first delivery. Without it we
    process the event: settling is idempotent, and a duplicate settle is
    harmless where a dropped one loses a customer's payment.
    """
    from app import webhook

    outcome = await webhook.handle_event(session, None, {
        "id": "evt_2", "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_123"}},
    })
    assert outcome != "duplicate"
    await session.refresh(authorized_payment)
    assert authorized_payment.status == PaymentTxStatus.SUCCEEDED.value


async def test_settling_publishes_rather_than_calling_orders(session, authorized_payment):
    """Money moved and that fact is durable here; the order is advanced by the
    orders service when it reads this. A direct call would let a slow orders
    service fail a confirmation that already happened."""
    import json

    from app import webhook
    from app.models import OutboxEvent

    await webhook.handle_event(session, None, {
        "id": "evt_3", "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_123"}},
    })

    events = [
        json.loads(e.payload)
        for e in await session.scalars(
            select(OutboxEvent).where(OutboxEvent.topic == "payment-events")
        )
    ]
    assert events and events[-1]["payment_status"] == "SUCCEEDED"


# ---- payment commands -----------------------------------------------------
#
# Orders records "settle this" or "refund this" in its own transaction, and this
# service carries it out. Before the handler existed the intents were published
# and nothing acted on them — so a cancelled card order showed as refunded in the
# order history while the customer's money stayed put.


async def test_a_settle_command_captures(session):
    await consumer._apply_order_event(session, _order_event(status="PAYMENT_SUCCESS"))
    payment = await service.get_payment(session, 1)
    payment.status = PaymentTxStatus.AUTHORIZED.value
    await session.commit()

    await consumer._apply_payment_command(session, {"order_id": 1, "action": "settle"})
    await session.refresh(payment)
    assert payment.status == PaymentTxStatus.SUCCEEDED.value


async def test_a_replayed_settle_is_a_no_op(session):
    await consumer._apply_order_event(session, _order_event(status="PAYMENT_SUCCESS"))
    payment = await service.get_payment(session, 1)
    payment.status = PaymentTxStatus.AUTHORIZED.value
    await session.commit()

    for _ in range(3):
        await consumer._apply_payment_command(session, {"order_id": 1, "action": "settle"})
    await session.refresh(payment)
    assert payment.status == PaymentTxStatus.SUCCEEDED.value


async def test_a_command_before_its_order_is_retried_not_dropped(session):
    """Topics have no ordering between them, so the command can arrive first.

    Raising leaves it unacknowledged and it comes back once the snapshot lands.
    Swallowing it would lose a refund silently, which is the worst option here.
    """
    with pytest.raises(LookupError):
        await consumer._apply_payment_command(session, {"order_id": 99, "action": "refund"})


async def test_an_unknown_command_is_ignored_not_retried(session):
    """A command we do not understand will never succeed, so it must not block
    the subscription forever."""
    await consumer._apply_order_event(session, _order_event())
    await consumer._apply_payment_command(session, {"order_id": 1, "action": "levitate"})

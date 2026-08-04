"""Outbound delivery of order-status changes: preferences, fan-out, audit trail."""
from decimal import Decimal

import pytest

from src.modules.notifications import preferences, service
from src.modules.notifications.schemas import PreferenceUpdate
from src.modules.orders.models import Order, OrderStatus
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister

EMAIL = "reach@example.com"
PHONE = "+15559820001"


class _Recorder:
    """Stands in for senders.dispatch, recording every call."""

    def __init__(self, result: bool = True):
        self.result = result
        self.calls: list[tuple[str, str, str, str | None]] = []

    async def __call__(self, channel, to, message, subject=None):
        self.calls.append((channel, to, message, subject))
        return self.result

    def channels(self) -> set[str]:
        return {c for c, *_ in self.calls}

    def recipients(self, channel: str) -> list[str]:
        return [to for c, to, *_ in self.calls if c == channel]


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(service.senders, "dispatch", rec)
    return rec


async def _customer(db_session):
    return await users_service.register_user(
        db_session,
        UserRegister(email=EMAIL, phone=PHONE, first_name="R", last_name="C",
                     password="supersecret1", role="customer"),
    )


async def _order(db_session, status: OrderStatus) -> Order:
    customer = await _customer(db_session)
    order = Order(customer_id=customer.id, restaurant_id=1, address_id=1,
                  status=status.value, subtotal=Decimal("10"), total=Decimal("10"))
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_confirmation_emails_the_customer(db_session, recorder):
    order = await _order(db_session, OrderStatus.PAYMENT_SUCCESS)

    await service.deliver_order_status(db_session, order)

    assert "EMAIL" in recorder.channels()
    assert recorder.recipients("EMAIL") == [EMAIL]
    # Subject names the order, so it is findable in an inbox.
    assert f"#{order.id}" in recorder.calls[0][3]


@pytest.mark.asyncio
async def test_sms_is_not_sent_until_the_customer_opts_in(db_session, recorder):
    order = await _order(db_session, OrderStatus.OUT_FOR_DELIVERY)

    await service.deliver_order_status(db_session, order)

    assert "SMS" not in recorder.channels()


@pytest.mark.asyncio
async def test_sms_is_sent_to_the_phone_once_enabled(db_session, recorder):
    order = await _order(db_session, OrderStatus.OUT_FOR_DELIVERY)
    await preferences.update_preferences(
        db_session, order.customer_id, PreferenceUpdate(sms_enabled=True)
    )

    await service.deliver_order_status(db_session, order)

    assert recorder.recipients("SMS") == [PHONE]


@pytest.mark.asyncio
async def test_disabling_email_stops_the_email(db_session, recorder):
    order = await _order(db_session, OrderStatus.PAYMENT_SUCCESS)
    await preferences.update_preferences(
        db_session, order.customer_id, PreferenceUpdate(email_enabled=False)
    )

    await service.deliver_order_status(db_session, order)

    assert "EMAIL" not in recorder.channels()


@pytest.mark.asyncio
async def test_push_fans_out_across_every_registered_device(db_session, recorder):
    order = await _order(db_session, OrderStatus.PREPARING)
    for token in ("tok-phone001", "tok-tablet01"):
        await preferences.register_device(db_session, order.customer_id, token)

    await service.deliver_order_status(db_session, order)

    assert sorted(recorder.recipients("PUSH")) == ["tok-phone001", "tok-tablet01"]


@pytest.mark.asyncio
async def test_push_with_no_registered_device_is_a_silent_skip(db_session, recorder):
    """Nothing to send to is not a failure, and must not record one."""
    order = await _order(db_session, OrderStatus.PREPARING)

    rows = await service.deliver_order_status(db_session, order)

    assert recorder.calls == []
    assert rows == []


@pytest.mark.asyncio
async def test_intermediate_status_sends_no_email_or_sms(db_session, recorder):
    order = await _order(db_session, OrderStatus.PREPARING)
    await preferences.update_preferences(
        db_session, order.customer_id, PreferenceUpdate(sms_enabled=True)
    )
    await preferences.register_device(db_session, order.customer_id, "tok-phone001")

    await service.deliver_order_status(db_session, order)

    assert recorder.channels() == {"PUSH"}


@pytest.mark.asyncio
async def test_a_status_with_no_outbound_copy_sends_nothing(db_session, recorder):
    """PAYMENT_PENDING is an internal step; the customer hears nothing for it."""
    order = await _order(db_session, OrderStatus.PAYMENT_PENDING)

    assert await service.deliver_order_status(db_session, order) == []
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_each_attempt_is_recorded_as_delivered(db_session, recorder):
    order = await _order(db_session, OrderStatus.DELIVERED)

    rows = await service.deliver_order_status(db_session, order)

    assert rows and all(row.delivered for row in rows)
    assert all(row.order_id == order.id for row in rows)


@pytest.mark.asyncio
async def test_a_failed_send_is_recorded_rather_than_lost(db_session, monkeypatch):
    """A bounced email stays visible in the audit trail instead of only in logs."""
    monkeypatch.setattr(service.senders, "dispatch", _Recorder(result=False))
    order = await _order(db_session, OrderStatus.DELIVERED)

    rows = await service.deliver_order_status(db_session, order)

    assert rows and not any(row.delivered for row in rows)


@pytest.mark.asyncio
async def test_a_sender_that_raises_does_not_break_the_order(db_session, monkeypatch):
    """The order is already delivered; a broken provider cannot undo that."""
    async def exploding(channel, to, message, subject=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(service.senders, "dispatch", exploding)
    order = await _order(db_session, OrderStatus.DELIVERED)

    rows = await service.deliver_order_status(db_session, order)

    assert rows and not any(row.delivered for row in rows)


@pytest.mark.asyncio
async def test_outbound_rows_stay_out_of_the_in_app_feed(db_session, recorder):
    """Otherwise one status change would appear up to three times in the feed."""
    order = await _order(db_session, OrderStatus.DELIVERED)
    service.notify_order_status(db_session, order)
    await db_session.commit()

    await service.deliver_order_status(db_session, order)

    feed = await service.list_for_user(db_session, order.customer_id)
    assert [n.channel for n in feed] == ["LOG"]
    # ...and are reachable on their own endpoint.
    deliveries = await service.list_deliveries(db_session, order.customer_id)
    assert deliveries and all(n.channel != "LOG" for n in deliveries)

"""Stripe webhook: signature verification and event handling."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.config import settings
from src.modules.orders.models import (
    Actor, Order, OrderItem, OrderStatus, PaymentStatus,
)
from src.modules.orders.state_machine import apply_transition
from src.modules.payments.models import Payment, PaymentTxStatus
from src.modules.restaurants.models import MenuCategory, MenuItem, Restaurant
from src.modules.users.models import Address, User

SECRET = "whsec_test_secret"
INTENT = "pi_test_999"
SESSION = "cs_test_999"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)


def _sign(payload: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _event(event_type: str, intent: str = INTENT, event_id: str = "evt_1") -> bytes:
    return json.dumps({
        "id": event_id,
        "type": event_type,
        "data": {"object": {"id": intent, "object": "payment_intent"}},
    }).encode()


def _session_event(
    event_type: str,
    session_id: str = SESSION,
    intent: str | None = INTENT,
    payment_status: str = "paid",
    event_id: str = "evt_cs_1",
) -> bytes:
    """A hosted-Checkout event, as Stripe sends it after the redirect flow."""
    return json.dumps({
        "id": event_id,
        "type": event_type,
        "data": {"object": {
            "id": session_id, "object": "checkout.session",
            "payment_intent": intent, "payment_status": payment_status,
        }},
    }).encode()


async def _pending_card_order(session, provider_ref: str = INTENT) -> Order:
    """An order sitting at PAYMENT_PENDING with a Stripe reference recorded."""
    session.add(User(id=1, email="c@x.com", phone="+1", first_name="c", last_name="u",
                     hashed_password="h", role="customer"))
    session.add(User(id=2, email="o@x.com", phone="+2", first_name="o", last_name="w",
                     hashed_password="h", role="restaurant"))
    session.add(Restaurant(id=1, owner_id=2, name="R", city="C", address_line="1", phone="+1"))
    session.add(Address(id=1, user_id=1, label="home", line1="1", city="C", postal_code="1"))
    session.add(MenuCategory(id=1, restaurant_id=1, name="M"))
    session.add(MenuItem(id=1, restaurant_id=1, category_id=1, name="Pizza", price=Decimal("10")))

    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.CREATED.value, payment_method="CARD",
                  payment_status=PaymentStatus.PENDING.value,
                  subtotal=Decimal("10"), total=Decimal("10"))
    order.items.append(OrderItem(menu_item_id=1, name="Pizza", unit_price=Decimal("10"),
                                 quantity=1, line_total=Decimal("10")))
    session.add(order)
    await session.flush()
    apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
    session.add(Payment(order_id=order.id, provider="CARD", amount=Decimal("10"),
                        status=PaymentTxStatus.PENDING.value, provider_ref=provider_ref,
                        idempotency_key=f"order-{order.id}"))
    await session.commit()
    return order


async def _post(api_client, payload: bytes, signature: str | None):
    headers = {"content-type": "application/json"}
    if signature is not None:
        headers["stripe-signature"] = signature
    return await api_client.post("/payments/webhook", content=payload, headers=headers)


@pytest.mark.asyncio
async def test_succeeded_event_marks_the_order_paid(api_client, app_session):
    order = await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200, resp.text
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_SUCCESS.value
    assert order.payment_status == PaymentStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_succeeded_event_marks_the_payment_succeeded(api_client, app_session):
    order = await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded")

    await _post(api_client, payload, _sign(payload))

    payment = await app_session.scalar(
        select(Payment).where(Payment.order_id == order.id)
    )
    await app_session.refresh(payment)
    assert payment.status == PaymentTxStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_a_forged_signature_is_rejected(api_client, app_session):
    await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded")

    resp = await _post(api_client, payload, _sign(payload, secret="whsec_wrong"))

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_missing_signature_is_rejected(api_client, app_session):
    await _pending_card_order(app_session)

    resp = await _post(api_client, _event("payment_intent.succeeded"), None)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_tampered_body_is_rejected(api_client, app_session):
    await _pending_card_order(app_session)
    signature = _sign(_event("payment_intent.succeeded"))

    # Same signature, different body.
    resp = await _post(api_client, _event("payment_intent.payment_failed"), signature)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_stale_timestamp_is_rejected(api_client, app_session):
    """A captured request must not be replayable hours later."""
    await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded")
    old = int(time.time()) - 3600

    resp = await _post(api_client, payload, _sign(payload, timestamp=old))

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_replaying_an_event_changes_nothing(api_client, app_session):
    order = await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded")

    first = await _post(api_client, payload, _sign(payload))
    second = await _post(api_client, payload, _sign(payload))

    assert first.status_code == 200
    assert second.status_code == 200
    await app_session.refresh(order, ["events"])
    paid_events = [e for e in order.events if e.to_status == OrderStatus.PAYMENT_SUCCESS.value]
    assert len(paid_events) == 1


@pytest.mark.asyncio
async def test_failure_event_leaves_the_order_payable(api_client, app_session):
    order = await _pending_card_order(app_session)
    payload = _event("payment_intent.payment_failed")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_PENDING.value
    payment = await app_session.scalar(
        select(Payment).where(Payment.order_id == order.id)
    )
    await app_session.refresh(payment)
    assert payment.status == PaymentTxStatus.FAILED.value


@pytest.mark.asyncio
async def test_unknown_event_types_are_accepted_and_ignored(api_client, app_session):
    """Anything not 2xx makes Stripe retry forever."""
    order = await _pending_card_order(app_session)
    payload = _event("charge.dispute.created", event_id="evt_other")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_PENDING.value


@pytest.mark.asyncio
async def test_event_for_an_unknown_intent_is_accepted(api_client, app_session):
    await _pending_card_order(app_session)
    payload = _event("payment_intent.succeeded", intent="pi_not_ours", event_id="evt_2")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_completed_checkout_session_marks_the_order_paid(api_client, app_session):
    """The redirect flow settles on the session event, not the intent event."""
    order = await _pending_card_order(app_session, provider_ref=SESSION)
    payload = _session_event("checkout.session.completed")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200, resp.text
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_SUCCESS.value
    assert order.payment_status == PaymentStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_completed_session_records_the_intent_for_refunds(api_client, app_session):
    """A refund cannot be issued against a ``cs_`` id, so the row has to move on
    to the PaymentIntent the session created."""
    order = await _pending_card_order(app_session, provider_ref=SESSION)
    payload = _session_event("checkout.session.completed")

    await _post(api_client, payload, _sign(payload))

    payment = await app_session.scalar(select(Payment).where(Payment.order_id == order.id))
    await app_session.refresh(payment)
    assert payment.provider_ref == INTENT
    assert payment.status == PaymentTxStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_an_unpaid_completed_session_does_not_settle(api_client, app_session):
    """A delayed payment method completes the session while still unpaid; the
    money has not moved, so the order must not reach the kitchen yet."""
    order = await _pending_card_order(app_session, provider_ref=SESSION)
    payload = _session_event("checkout.session.completed", payment_status="unpaid")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_PENDING.value
    payment = await app_session.scalar(select(Payment).where(Payment.order_id == order.id))
    await app_session.refresh(payment)
    # The intent is still recorded — only the settlement waits.
    assert payment.provider_ref == INTENT
    assert payment.status == PaymentTxStatus.PENDING.value


@pytest.mark.asyncio
async def test_async_payment_failure_leaves_the_order_payable(api_client, app_session):
    order = await _pending_card_order(app_session, provider_ref=SESSION)
    payload = _session_event("checkout.session.async_payment_failed")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 200
    await app_session.refresh(order)
    assert order.status == OrderStatus.PAYMENT_PENDING.value
    payment = await app_session.scalar(select(Payment).where(Payment.order_id == order.id))
    await app_session.refresh(payment)
    assert payment.status == PaymentTxStatus.FAILED.value


@pytest.mark.asyncio
async def test_intent_event_after_the_session_event_changes_nothing(api_client, app_session):
    """Stripe sends both. Whichever lands second finds the order already paid."""
    order = await _pending_card_order(app_session, provider_ref=SESSION)
    session_payload = _session_event("checkout.session.completed")
    intent_payload = _event("payment_intent.succeeded", event_id="evt_pi_after")

    await _post(api_client, session_payload, _sign(session_payload))
    resp = await _post(api_client, intent_payload, _sign(intent_payload))

    assert resp.status_code == 200
    await app_session.refresh(order, ["events"])
    paid_events = [e for e in order.events if e.to_status == OrderStatus.PAYMENT_SUCCESS.value]
    assert len(paid_events) == 1


@pytest.mark.asyncio
async def test_webhook_is_refused_when_no_secret_is_configured(api_client, monkeypatch):
    """Without a configured secret nothing can be verified, so nothing is trusted."""
    monkeypatch.setattr(settings, "stripe_webhook_secret", None)
    payload = _event("payment_intent.succeeded")

    resp = await _post(api_client, payload, _sign(payload))

    assert resp.status_code == 400

import pytest

from src.modules.orders.models import Actor, OrderStatus, RefundStatus
from src.modules.orders import state_machine as sm


def test_legal_transition_passes():
    sm.assert_transition_allowed(OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING)  # no raise


def test_skipping_transition_rejected():
    with pytest.raises(sm.OrderError) as exc:
        sm.assert_transition_allowed(OrderStatus.CREATED, OrderStatus.OUT_FOR_DELIVERY)
    assert exc.value.details["code"] == "ILLEGAL_TRANSITION"


def test_terminal_states_reject_all():
    for terminal in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
        with pytest.raises(sm.OrderError):
            sm.assert_transition_allowed(terminal, OrderStatus.PREPARING)


@pytest.mark.parametrize("status,expected", [
    (OrderStatus.CREATED, True), (OrderStatus.RESTAURANT_ACCEPTED, True),
    (OrderStatus.PREPARING, False), (OrderStatus.OUT_FOR_DELIVERY, False),
])
def test_customer_cancel_window(status, expected):
    assert sm.customer_cancel_allowed(status) is expected


@pytest.mark.parametrize("status,actor,expected", [
    (OrderStatus.PAYMENT_SUCCESS, Actor.CUSTOMER, RefundStatus.FULL),
    (OrderStatus.PREPARING, Actor.RESTAURANT, RefundStatus.NONE),
    (OrderStatus.PAYMENT_SUCCESS, Actor.RESTAURANT, RefundStatus.FULL),
    (OrderStatus.PREPARING, Actor.SYSTEM, RefundStatus.FULL),
])
def test_refund_matrix(status, actor, expected):
    assert sm.refund_on_cancel(status, actor) is expected

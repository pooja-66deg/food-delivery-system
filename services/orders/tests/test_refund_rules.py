"""What gets refunded on a cancellation, and when the command is published.

Both properties here were live defects. They are related, and the second is why
the first became urgent: the refund command was recorded *after* the commit that
justified it, so it was discarded with the session and never reached the payments
service. That masked the refund rule being wrong — orders claimed REFUNDED, and
because nothing was delivered, nothing tried to move money that was never taken.

Fixing the ordering removes the mask. So the rule has to be right too.
"""

from decimal import Decimal

from app.models import Actor, OrderStatus, RefundStatus
from app.state_machine import UNPAID_STATES, refund_on_cancel


class TestRefundOnCancel:
    """Nothing captured means nothing to refund, whoever cancels."""

    def test_unpaid_states_are_the_pre_capture_ones(self):
        # PAYMENT_SUCCESS is the transition that marks money captured (or, for
        # COD, committed to be collected), so it must not be in this set.
        assert UNPAID_STATES == {OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING}

    def test_customer_cancelling_an_unpaid_order_refunds_nothing(self):
        """The live defect: a CARD order whose Stripe authorize failed sits in
        PAYMENT_PENDING, and cancelling it booked a FULL refund of money the
        platform never took."""
        for state in (OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING):
            assert refund_on_cancel(state, Actor.CUSTOMER) == RefundStatus.NONE

    def test_system_expiry_of_an_unpaid_order_refunds_nothing(self):
        # expire_unpaid_orders already said this in a comment; now the rule holds
        # wherever the decision is made rather than only on that one path.
        assert refund_on_cancel(
            OrderStatus.PAYMENT_PENDING, Actor.SYSTEM
        ) == RefundStatus.NONE

    def test_restaurant_rejecting_an_unpaid_order_refunds_nothing(self):
        assert refund_on_cancel(
            OrderStatus.PAYMENT_PENDING, Actor.RESTAURANT
        ) == RefundStatus.NONE

    def test_a_paid_order_still_refunds_in_full(self):
        """The fix must not stop real refunds — this is the case that matters."""
        for actor in (Actor.CUSTOMER, Actor.SYSTEM, Actor.RESTAURANT):
            assert refund_on_cancel(
                OrderStatus.PAYMENT_SUCCESS, actor
            ) == RefundStatus.FULL

    def test_restaurant_cancelling_after_prep_started_refunds_nothing(self):
        # Unchanged behaviour, pinned so the added branch cannot swallow it.
        assert refund_on_cancel(
            OrderStatus.PREPARING, Actor.RESTAURANT
        ) == RefundStatus.NONE

    def test_customer_cancelling_a_paid_accepted_order_refunds_in_full(self):
        assert refund_on_cancel(
            OrderStatus.RESTAURANT_ACCEPTED, Actor.CUSTOMER
        ) == RefundStatus.FULL


class TestPaymentCommandIsTransactional:
    """The refund/settle command must be in the same transaction as the status
    change that justified it."""

    def test_every_payment_action_is_recorded_before_its_commit(self):
        """Guards the ordering by reading the source, because the failure mode is
        invisible in a unit test with a single session: the outbox row is written
        either way, and only a real request scope discards it.

        ``_request_payment_action``'s own docstring promises it "commits with the
        status change that justified it". It did not — every call sat one line
        after ``await session.commit()``, so the row landed in a fresh
        transaction that the request-scoped session then threw away. Orders
        reported REFUNDED while the payments row stayed AUTHORIZED, permanently.
        """
        import inspect

        from app import service

        lines = inspect.getsource(service).splitlines()
        pending_commit = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("await session.commit()"):
                pending_commit = True
            elif stripped.startswith("_request_payment_action("):
                assert not pending_commit, (
                    f"line {i + 1}: _request_payment_action follows a commit — the "
                    "outbox row will be discarded with the session"
                )
            elif stripped.startswith(("async def ", "def ")):
                pending_commit = False


class TestRefundAmountBookkeeping:
    """A NONE refund must not also stamp an amount or flip payment_status."""

    def test_record_refund_none_leaves_payment_status_alone(self):
        from app.models import Order, PaymentStatus
        from app.service import _record_refund

        order = Order(
            customer_id=1, restaurant_id=1, address_id=1,
            status=OrderStatus.PAYMENT_PENDING.value,
            payment_method="CARD", payment_status=PaymentStatus.PENDING.value,
            subtotal=Decimal("200.00"), delivery_fee=Decimal("0"),
            total=Decimal("200.00"),
        )
        _record_refund(order, RefundStatus.NONE)

        assert order.refund_status == RefundStatus.NONE.value
        assert order.refund_amount == Decimal("0")
        assert order.payment_status == PaymentStatus.PENDING.value

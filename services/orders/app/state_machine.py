"""Central order state machine: legal transitions + COD refund rules."""
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import AppException
from app.models import Actor, Order, OrderStatus, OrderStatusEvent, RefundStatus

S = OrderStatus

ALLOWED: dict[OrderStatus, set[OrderStatus]] = {
    S.CREATED: {S.PAYMENT_PENDING, S.CANCELLED},
    S.PAYMENT_PENDING: {S.PAYMENT_SUCCESS, S.CANCELLED},
    S.PAYMENT_SUCCESS: {S.RESTAURANT_ACCEPTED, S.CANCELLED, S.REJECTED},
    S.RESTAURANT_ACCEPTED: {S.PREPARING, S.CANCELLED},
    S.PREPARING: {S.READY_FOR_PICKUP, S.CANCELLED},
    S.READY_FOR_PICKUP: {S.OUT_FOR_DELIVERY, S.CANCELLED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED, S.CANCELLED},
    S.DELIVERED: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
    S.REJECTED: set(),
}

PRE_PREP_STATES: set[OrderStatus] = {
    S.CREATED, S.PAYMENT_PENDING, S.PAYMENT_SUCCESS, S.RESTAURANT_ACCEPTED,
}

#: States an order can be cancelled from where no money has been taken yet.
#: PAYMENT_SUCCESS is deliberately *not* here — that is the transition that marks
#: the money captured (or, for COD, committed to be collected).
UNPAID_STATES: set[OrderStatus] = {S.CREATED, S.PAYMENT_PENDING}


class OrderError(AppException):
    """A client-actionable order error; ``code`` is a stable machine reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message, status_code=409, details={"code": code})
        self.code = code


def assert_transition_allowed(current: OrderStatus, to: OrderStatus) -> None:
    if to not in ALLOWED[OrderStatus(current)]:
        raise OrderError(
            "ILLEGAL_TRANSITION",
            f"Cannot move order from {OrderStatus(current).value} to {OrderStatus(to).value}.",
        )


def apply_transition(
    session: AsyncSession, order: Order, to: OrderStatus, actor: Actor, reason: str | None = None
) -> None:
    """Validate + apply a status change and append an audit event. No commit."""
    assert_transition_allowed(OrderStatus(order.status), to)
    session.add(
        OrderStatusEvent(
            order_id=order.id, from_status=order.status, to_status=to.value,
            actor=actor.value, reason=reason,
        )
    )
    order.status = to.value


def customer_cancel_allowed(current: OrderStatus) -> bool:
    return OrderStatus(current) in PRE_PREP_STATES


def refund_on_cancel(current: OrderStatus, actor: Actor) -> RefundStatus:
    """What to refund when an order is cancelled from ``current`` by ``actor``.

    Nothing captured means nothing to refund, whoever cancels and for whatever
    reason — expire_unpaid_orders already said so in as many words ("Nothing was
    ever captured, so there is nothing to refund"), but the customer- and
    restaurant-initiated paths through here did not, and returned FULL from
    PAYMENT_PENDING anyway. That booked a refund of money the platform never
    took: an order whose Stripe authorize had failed reported refund_status FULL
    against a payment row still marked FAILED, so refund reporting could not
    balance against the provider. Now the payment command is published in the
    same transaction as the cancellation, that phantom refund would also be
    *delivered* to the payments service, so this has to be decided here.
    """
    if OrderStatus(current) in UNPAID_STATES:
        return RefundStatus.NONE
    if actor in (Actor.SYSTEM, Actor.CUSTOMER):
        return RefundStatus.FULL
    # RESTAURANT approval
    return RefundStatus.FULL if OrderStatus(current) in PRE_PREP_STATES else RefundStatus.NONE

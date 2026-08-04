"""Order lifecycle service."""
from datetime import datetime, timedelta
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.core.exceptions import AppException, ForbiddenException, NotFoundException
from src.modules.cart import checkout as checkout_service
from src.modules.cart import service as cart_service
from src.modules.cart.schemas import CheckoutRequest
from src.modules.orders import state_machine as sm
from src.modules.orders.models import (
    Actor, Order, OrderItem, OrderStatus, OrderStatusEvent, PaymentMethod, PaymentStatus,
    RefundStatus,
)
from src.modules.orders.state_machine import OrderError
from src.modules.events import outbox
from src.modules.notifications import service as notification_service
from src.modules.payments import service as payment_service
from src.modules.payments.models import PaymentTxStatus
from src.modules.restaurants import inventory
from src.modules.restaurants import service as restaurant_service
from src.modules.restaurants.models import Restaurant

_LOCK_KEY = "order_lock:{user_id}"
_LOCK_TTL = 10


async def _restore_stock(session: AsyncSession, order: Order) -> None:
    """Put a cancelled order's stock back, in the caller's transaction.

    The lines are queried rather than read off ``order.items`` because the
    cancel paths fetch the order with ``session.get`` and lazy loading is not
    available on an async session.
    """
    lines = list(await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    await inventory.restore_order(session, lines)


def _emit_status(session: AsyncSession, order: Order) -> None:
    """Queue a customer notification and an outbox event for the order's current
    status, in the caller's transaction (outbox pattern — same tx as the state
    change). Caller commits."""
    notification_service.notify_order_status(session, order)
    outbox.record_event(
        session, "order-events", str(order.id),
        {"order_id": order.id, "status": order.status, "customer_id": order.customer_id},
    )


async def _deliver_status(session: AsyncSession, *orders: Order) -> None:
    """Send the outbound (email/SMS/push) copies of a status change.

    **Call only after the commit.** ``_emit_status`` writes the in-app row inside
    the transaction; this sends the messages that cannot be un-sent, so it waits
    until the status change is durable. Kept as the last step of each lifecycle
    function for the same reason: a notification must never delay or interleave
    with the payment work the status change triggers.
    """
    for order in orders:
        await notification_service.deliver_order_status(session, order)


async def _notify_restaurant(session: AsyncSession, order: Order) -> None:
    """Tell the owner an order is waiting. Only ever called for a paid order —
    the kitchen must not start cooking something nobody has paid for."""
    restaurant = await session.get(Restaurant, order.restaurant_id)
    if restaurant is not None:
        notification_service.add_notification(
            session, restaurant.owner_id, "order.new",
            f"New order #{order.id} — {order.total} to prepare.", order.id,
        )


async def mark_paid(session: AsyncSession, order_id: int) -> Order:
    """Move an order from PAYMENT_PENDING to PAYMENT_SUCCESS.

    Called by the payments webhook once money has actually moved, and by
    checkout when the provider settles without the customer's involvement.
    Idempotent: an order that is already past payment is returned untouched.
    """
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    if order.status != OrderStatus.PAYMENT_PENDING.value:
        return await _load_full(session, order_id)

    sm.apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM,
                        reason="payment confirmed")
    order.payment_status = PaymentStatus.SUCCESS.value
    _emit_status(session, order)
    await _notify_restaurant(session, order)
    await session.commit()
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def _load_full(session: AsyncSession, order_id: int) -> Order:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.events))
    )
    return (await session.scalars(stmt)).one()


async def create_order_from_checkout(
    redis: Redis, session: AsyncSession, user, request: CheckoutRequest
) -> Order:
    lock_key = _LOCK_KEY.format(user_id=user.id)
    acquired = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL)
    if not acquired:
        raise OrderError("CHECKOUT_IN_PROGRESS", "A checkout is already in progress.")
    try:
        validated = await checkout_service.validate_checkout(redis, session, user, request)

        order = Order(
            customer_id=user.id,
            restaurant_id=validated.restaurant_id,
            address_id=validated.address_id,
            status=OrderStatus.CREATED.value,
            payment_method=request.payment_method,
            payment_status=PaymentStatus.PENDING.value,
            subtotal=validated.subtotal,
            delivery_fee=Decimal("0"),
            total=validated.subtotal,
        )
        for it in validated.items:
            order.items.append(
                OrderItem(menu_item_id=it.menu_item_id, name=it.name,
                          unit_price=it.unit_price, quantity=it.quantity, line_total=it.line_total)
            )
        session.add(order)
        await session.flush()  # assign order.id before writing events

        # Take the stock in the same transaction as the order itself.
        await inventory.apply_order(session, validated.items)

        # Record the CREATED baseline event, then advance as far as the payment
        # method allows. COD is collected on delivery, so it counts as settled
        # now; a card order waits until the customer has actually paid.
        session.add(
            OrderStatusEvent(order_id=order.id, from_status=None,
                             to_status=OrderStatus.CREATED.value, actor=Actor.SYSTEM.value)
        )
        sm.apply_transition(session, order, OrderStatus.PAYMENT_PENDING, Actor.SYSTEM)
        if order.payment_method == PaymentMethod.COD.value:
            sm.apply_transition(session, order, OrderStatus.PAYMENT_SUCCESS, Actor.SYSTEM,
                                reason="COD: to be collected on delivery")
            order.payment_status = PaymentStatus.SUCCESS.value

        _emit_status(session, order)
        if order.status == OrderStatus.PAYMENT_SUCCESS.value:
            await _notify_restaurant(session, order)
        await session.commit()
        await cart_service.clear_cart(redis, user.id)
        loaded = await _load_full(session, order.id)

        # Announce the confirmation now, before the payment setup below. A COD
        # order is already PAYMENT_SUCCESS and gets its confirmation here; a card
        # order is still PAYMENT_PENDING, which has no outbound copy, so this is
        # a no-op for it and ``mark_paid`` announces it once the money lands.
        await _deliver_status(session, loaded)

        # Set up the payment — idempotent per order. A provider that needs the
        # customer to confirm hands back a secret; one that settles by itself
        # does not, and the order is done the moment it is authorized.
        payment = await payment_service.create_payment_for_order(session, loaded)
        secret = payment_service.client_secret_of(payment)
        if (
            loaded.status == OrderStatus.PAYMENT_PENDING.value
            and secret is None
            and payment.status != PaymentTxStatus.FAILED.value
        ):
            loaded = await mark_paid(session, loaded.id)

        # Transient, response-only: the secret is handed to the browser and
        # never written to the database.
        loaded.payment_client_secret = secret
        return loaded
    finally:
        await redis.delete(lock_key)


# An order in one of these has nothing left to happen to it.
FINISHED = (
    OrderStatus.DELIVERED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
)


async def list_orders(
    session: AsyncSession, customer_id: int, limit: int = 20, offset: int = 0,
    scope: str = "all",
):
    """A customer's orders, newest first.

    ``scope`` splits the list the way the orders tab does: "active" is anything
    still in flight, "past" is everything finished. Filtering here rather than
    in the client keeps pagination honest.
    """
    stmt = (
        select(Order)
        .where(Order.customer_id == customer_id)
        .options(selectinload(Order.items), selectinload(Order.events))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if scope == "active":
        stmt = stmt.where(Order.status.notin_(FINISHED))
    elif scope == "past":
        stmt = stmt.where(Order.status.in_(FINISHED))
    return list(await session.scalars(stmt.limit(limit).offset(offset)))


async def list_orders_for_restaurant(
    session: AsyncSession, user, restaurant_id: int, limit: int = 50, offset: int = 0
) -> list[Order]:
    """Orders for a restaurant the caller owns (or admin), newest first.

    Unpaid orders are withheld: a card order that has not been paid for yet may
    never be, and the kitchen must not start cooking it.
    """
    await restaurant_service.owned_restaurant(session, user, restaurant_id)  # 404/403
    stmt = (
        select(Order)
        .where(Order.restaurant_id == restaurant_id)
        .where(Order.status.notin_((
            OrderStatus.CREATED.value, OrderStatus.PAYMENT_PENDING.value,
        )))
        .options(selectinload(Order.items), selectinload(Order.events))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit).offset(offset)
    )
    return list(await session.scalars(stmt))


async def get_order_for_user(session: AsyncSession, user, order_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    if user.id == order.customer_id or user.role == "admin":
        return await _load_full(session, order_id)
    try:
        await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    except AppException:
        raise ForbiddenException("You cannot view this order")
    return await _load_full(session, order_id)


def _record_refund(order: Order, refund: RefundStatus) -> None:
    order.refund_status = refund.value
    if refund == RefundStatus.FULL:
        order.refund_amount = order.total
        order.payment_status = PaymentStatus.REFUNDED.value
    else:
        order.refund_amount = Decimal("0")


async def cancel_by_customer(session: AsyncSession, user, order_id: int) -> Order:
    order = await get_order_for_user(session, user, order_id)
    current = OrderStatus(order.status)
    if not sm.customer_cancel_allowed(current):
        raise OrderError("CANCEL_NOT_ALLOWED",
                         "This order can no longer be cancelled without restaurant approval.")
    sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.CUSTOMER)
    order.cancelled_by = Actor.CUSTOMER.value
    refund = sm.refund_on_cancel(current, Actor.CUSTOMER)
    _record_refund(order, refund)
    await _restore_stock(session, order)
    _emit_status(session, order)
    await session.commit()
    if refund == RefundStatus.FULL:
        await payment_service.refund_payment(session, order)
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def accept_by_restaurant(session: AsyncSession, user, order_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    sm.apply_transition(session, order, OrderStatus.RESTAURANT_ACCEPTED, Actor.RESTAURANT)
    _emit_status(session, order)
    await session.commit()
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def reject_by_restaurant(session: AsyncSession, user, order_id: int, reason: str | None = None) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    sm.apply_transition(session, order, OrderStatus.REJECTED, Actor.RESTAURANT, reason)
    order.cancelled_by = Actor.RESTAURANT.value
    order.cancel_reason = reason
    _record_refund(order, RefundStatus.FULL)  # kitchen rejection always refunds
    await _restore_stock(session, order)
    _emit_status(session, order)
    await session.commit()
    await payment_service.refund_payment(session, order)
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def advance_status(session: AsyncSession, user, order_id: int, to: OrderStatus, redis=None) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await restaurant_service.owned_restaurant(session, user, order.restaurant_id)
    current = OrderStatus(order.status)
    sm.apply_transition(session, order, to, Actor.RESTAURANT)
    refund = RefundStatus.NONE
    if to == OrderStatus.CANCELLED:
        order.cancelled_by = Actor.RESTAURANT.value
        refund = sm.refund_on_cancel(current, Actor.RESTAURANT)
        _record_refund(order, refund)
        await _restore_stock(session, order)
    _emit_status(session, order)
    await session.commit()
    if to == OrderStatus.DELIVERED:
        await payment_service.settle_payment(session, order)
    elif refund == RefundStatus.FULL:
        await payment_service.refund_payment(session, order)
    if to == OrderStatus.READY_FOR_PICKUP:
        # Local import avoids an orders<->delivery import cycle.
        from src.modules.delivery import service as delivery_service
        await delivery_service.assign_for_order(session, order, redis=redis)
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def driver_advance(session: AsyncSession, order_id: int, to: OrderStatus) -> Order:
    """Advance an order on behalf of the assigned driver (OUT_FOR_DELIVERY /
    DELIVERED). Access is enforced by the delivery service before calling."""
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    sm.apply_transition(session, order, to, Actor.DRIVER)
    _emit_status(session, order)
    await session.commit()
    if to == OrderStatus.DELIVERED:
        await payment_service.settle_payment(session, order)
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def expire_unpaid_orders(session: AsyncSession, now: datetime) -> int:
    """Cancel card orders that were never paid for.

    Phase E reserves stock the moment an order is created, so an abandoned
    checkout would hold that reservation forever. Cancelling through the normal
    path restores it and tells the customer why.
    """
    cutoff = now - timedelta(seconds=settings.payment_window_seconds)
    stmt = select(Order).where(
        Order.status == OrderStatus.PAYMENT_PENDING.value,
        Order.updated_at < cutoff,
    )
    stale = list(await session.scalars(stmt))
    for order in stale:
        sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.SYSTEM,
                            reason="payment was not completed in time")
        order.cancelled_by = Actor.SYSTEM.value
        order.cancel_reason = "payment was not completed in time"
        # Nothing was ever captured, so there is nothing to refund.
        _record_refund(order, RefundStatus.NONE)
        await _restore_stock(session, order)
        _emit_status(session, order)
    await session.commit()
    await _deliver_status(session, *stale)
    return len(stale)


async def expire_pending_acceptances(session: AsyncSession, now: datetime) -> int:
    cutoff = now - timedelta(seconds=settings.restaurant_accept_timeout_seconds)
    stmt = select(Order).where(
        Order.status == OrderStatus.PAYMENT_SUCCESS.value,
        Order.updated_at < cutoff,
    )
    stale = list(await session.scalars(stmt))
    for order in stale:
        sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.SYSTEM,
                            reason="restaurant acceptance timeout")
        order.cancelled_by = Actor.SYSTEM.value
        _record_refund(order, RefundStatus.FULL)
        await _restore_stock(session, order)
        _emit_status(session, order)
    await session.commit()
    for order in stale:
        await payment_service.refund_payment(session, order)
    await _deliver_status(session, *stale)
    return len(stale)

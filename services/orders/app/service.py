"""Order lifecycle service."""
from datetime import datetime, timedelta
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import cart as cart_service
from app import checkout as checkout_service
from app import outbox
from app import state_machine as sm
from app.cart_schemas import CheckoutRequest
from app.config import settings
from app.models import (
    Actor, AddressSnapshot, CustomerSnapshot, Order, OrderItem, OrderStatus,
    OrderStatusEvent, PaymentMethod, PaymentStatus, RefundStatus,
    RestaurantSnapshot,
)
from app.state_machine import OrderError
from shared.errors import AppException, ForbiddenException, NotFoundException

# Wording for the in-app feed row. Kept here rather than imported from the
# notifications service: the copy belongs to whoever raises the event, and a
# shared module would couple the two deployments over a dictionary of strings.
_STATUS_COPY = {
    "PAYMENT_SUCCESS": "Your order is confirmed and awaiting the restaurant.",
    "RESTAURANT_ACCEPTED": "The restaurant accepted your order.",
    "PREPARING": "Your order is being prepared.",
    "READY_FOR_PICKUP": "Your order is ready and awaiting a driver.",
    "OUT_FOR_DELIVERY": "Your order is on the way!",
    "DELIVERED": "Your order has been delivered. Enjoy!",
    "COMPLETED": "Your order is complete.",
    "CANCELLED": "Your order was cancelled.",
    "REJECTED": "The restaurant could not accept your order.",
}


def templates_copy(status: str) -> str:
    """An unknown status still produces something a human can read, because a
    new status must never silence the feed."""
    return _STATUS_COPY.get(status, f"Order status: {status}")


def _notify(
    session: AsyncSession, user_id: int, type_: str, message: str, order_id: int | None
) -> None:
    """Queue a notification. An event, because that table belongs elsewhere now."""
    outbox.record_event(
        session, "notification-events", str(order_id) if order_id else None,
        {"user_id": user_id, "type": type_, "message": message, "order_id": order_id},
    )


async def _owned_restaurant(session: AsyncSession, user, restaurant_id: int) -> RestaurantSnapshot:
    """The restaurant, if this caller manages it. 404 before 403.

    Answered from the local read-model, so the owner dashboard does not depend
    on the restaurants service being up to load.
    """
    snapshot = await session.get(RestaurantSnapshot, restaurant_id)
    if snapshot is None:
        raise NotFoundException("Restaurant", str(restaurant_id))
    if snapshot.owner_id != user.user_id and user.role != "admin":
        raise ForbiddenException("You do not manage this restaurant")
    return snapshot


_LOCK_KEY = "order_lock:{user_id}"
_LOCK_TTL = 10


async def _restore_stock(session: AsyncSession, order: Order, auth_header: str = "") -> None:
    """Put a cancelled order's stock back.

    A call to the restaurants service now, not a local update — stock lives in
    its database. Deliberately after the cancellation commits and best-effort:
    see ``checkout.release_stock`` for why a failure here must not un-cancel an
    order the customer asked to cancel.

    The lines are queried rather than read off ``order.items`` because the cancel
    paths fetch the order with ``session.get`` and lazy loading is not available
    on an async session.
    """
    lines = list(await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    await checkout_service.release_stock(order.restaurant_id, lines, auth_header)


def _display_name(user) -> str:
    """A customer's public name: first name plus last initial, "Alex R.".

    Built here rather than by the consumer, so the format is decided once by the
    service that holds the real name.
    """
    if user is None:
        return ""
    return (user.display_name or "") if user is not None else ""


async def _emit_status(session: AsyncSession, order: Order) -> None:
    """Queue a customer notification and an outbox event for the order's current
    status, in the caller's transaction (outbox pattern — same tx as the state
    change). Caller commits."""
    _notify(session, order.customer_id, f"order.{order.status}",
            templates_copy(order.status), order.id)
    customer = await session.get(CustomerSnapshot, order.customer_id)
    # The two ends of the journey, for the delivery service's local snapshot. It
    # cannot resolve a restaurant or an address itself — both live in other
    # databases — and a driver has to be able to navigate while those services
    # are down. So the coordinates travel with the event.
    address = await session.get(AddressSnapshot, order.address_id)
    outbox.record_event(
        session, "order-events", str(order.id),
        {
            "order_id": order.id,
            "status": order.status,
            "customer_id": order.customer_id,
            # A display name only — "Alex R." — for a review byline. Where to
            # *contact* this customer is the notifications service's business,
            # resolved from its own contacts read-model, so no address travels
            # on this topic and settles in every consumer's database.
            "customer_name": _display_name(customer),
            "restaurant_id": order.restaurant_id,
            # The payments service prices from this rather than reading the
            # order: authorising a charge must not depend on the orders service
            # answering, or a blip there becomes a customer who cannot pay.
            "total": str(order.total),
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            # The restaurant's own coordinates are the restaurants service's
            # fact; delivery gets them from its own copy. What travels here is
            # the destination, which orders is the only service to know.
            "destination_latitude": address.latitude if address is not None else None,
            "destination_longitude": address.longitude if address is not None else None,
        },
    )


async def _deliver_status(session: AsyncSession, *orders: Order) -> None:  # noqa: D401
    """Send the outbound (email/SMS/push) copies of a status change.

    **Call only after the commit.** ``_emit_status`` writes the in-app row inside
    the transaction; this sends the messages that cannot be un-sent, so it waits
    until the status change is durable. Kept as the last step of each lifecycle
    function for the same reason: a notification must never delay or interleave
    with the payment work the status change triggers.

    """
    # Nothing to do: the notifications service reads the same order event and
    # sends the outbound copies itself. Kept as a no-op so the lifecycle
    # functions read the same as before and the sequencing stays documented.
    return None


async def _notify_restaurant(session: AsyncSession, order: Order) -> None:
    """Tell the owner an order is waiting. Only ever called for a paid order —
    the kitchen must not start cooking something nobody has paid for."""
    restaurant = await session.get(RestaurantSnapshot, order.restaurant_id)
    if restaurant is not None:
        _notify(session, restaurant.owner_id, "order.new",
                f"New order #{order.id} — {order.total} to prepare.", order.id)


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
    await _emit_status(session, order)
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
    redis: Redis,
    session: AsyncSession,
    user,
    request: CheckoutRequest,
    auth_header: str = "",
) -> Order:
    """Place an order.

    ``auth_header`` is the caller's own token, forwarded to the restaurants
    service for the one synchronous call checkout makes. Services here do not
    hold machine credentials — the called service applies the same rules to the
    same person, and a compromised service cannot act as everyone.
    """
    lock_key = _LOCK_KEY.format(user_id=user.user_id)
    acquired = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL)
    if not acquired:
        raise OrderError("CHECKOUT_IN_PROGRESS", "A checkout is already in progress.")
    try:
        cart = await cart_service.get_cart(redis, user.user_id)
        validated = await checkout_service.validate_checkout(
            session, cart, user.user_id, request, auth_header
        )

        order = Order(
            customer_id=user.user_id,
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

        # Stock was already reserved by the restaurants service, in the same
        # transaction as the checks that justified it. There is nothing to take
        # here — and nothing that could take it a second time.

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

        await _emit_status(session, order)
        if order.status == OrderStatus.PAYMENT_SUCCESS.value:
            await _notify_restaurant(session, order)
        await session.commit()
        await cart_service.clear_cart(redis, user.user_id)
        loaded = await _load_full(session, order.id)

        # Announce the confirmation now, before the payment setup below. A COD
        # order is already PAYMENT_SUCCESS and gets its confirmation here; a card
        # order is still PAYMENT_PENDING, which has no outbound copy, so this is
        # a no-op for it and ``mark_paid`` announces it once the money lands.
        await _deliver_status(session, loaded)

        # The payments service creates the payment when it reads the order
        # event. It was a direct call here, which meant a slow provider held up
        # order creation; now the order exists the moment it is valid.
        #
        # The consequence the frontend has to handle: a card order's hosted
        # checkout URL is no longer in this response. It polls
        # GET /payments/order/{id} for it — the same endpoint it already uses to
        # resume an unpaid order.
        loaded.payment_checkout_url = None
        return loaded
    finally:
        await redis.delete(lock_key)


def _request_payment_action(session: AsyncSession, order: Order, action: str) -> None:
    """Ask the payments service to settle or refund. Recorded, not called.

    The monolith called into payments and waited for the provider. Two problems
    once they are separate: a slow provider would hold a driver's "delivered" tap
    open, and the refund would be lost entirely if this transaction then rolled
    back. As an outbox event it commits with the status change that justified it,
    and the payments service does the provider work on its own time.

    What this gives up is the immediate answer. A refund is therefore "requested"
    rather than "done" at the moment the API responds — which is already true of
    every card refund, since the provider settles them asynchronously anyway.
    """
    outbox.record_event(
        session, "payment-commands", str(order.id),
        {"order_id": order.id, "action": action, "amount": str(order.total)},
    )


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
    await _owned_restaurant(session, user, restaurant_id)  # 404/403
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
    if user.user_id == order.customer_id or user.role == "admin":
        return await _load_full(session, order_id)
    try:
        await _owned_restaurant(session, user, order.restaurant_id)
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


async def cancel_by_customer(
    session: AsyncSession, user, order_id: int, auth_header: str = ""
) -> Order:
    order = await get_order_for_user(session, user, order_id)
    current = OrderStatus(order.status)
    if not sm.customer_cancel_allowed(current):
        raise OrderError("CANCEL_NOT_ALLOWED",
                         "This order can no longer be cancelled without restaurant approval.")
    sm.apply_transition(session, order, OrderStatus.CANCELLED, Actor.CUSTOMER)
    order.cancelled_by = Actor.CUSTOMER.value
    refund = sm.refund_on_cancel(current, Actor.CUSTOMER)
    _record_refund(order, refund)
    await _restore_stock(session, order, auth_header)
    await _emit_status(session, order)
    await session.commit()
    if refund == RefundStatus.FULL:
        _request_payment_action(session, order, "refund")
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def accept_by_restaurant(session: AsyncSession, user, order_id: int) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await _owned_restaurant(session, user, order.restaurant_id)
    sm.apply_transition(session, order, OrderStatus.RESTAURANT_ACCEPTED, Actor.RESTAURANT)
    await _emit_status(session, order)
    await session.commit()
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def reject_by_restaurant(
    session: AsyncSession, user, order_id: int, reason: str | None = None,
    auth_header: str = "",
) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await _owned_restaurant(session, user, order.restaurant_id)
    sm.apply_transition(session, order, OrderStatus.REJECTED, Actor.RESTAURANT, reason)
    order.cancelled_by = Actor.RESTAURANT.value
    order.cancel_reason = reason
    _record_refund(order, RefundStatus.FULL)  # kitchen rejection always refunds
    await _restore_stock(session, order, auth_header)
    await _emit_status(session, order)
    await session.commit()
    _request_payment_action(session, order, "refund")
    await _deliver_status(session, order)
    return await _load_full(session, order_id)


async def advance_status(session: AsyncSession, user, order_id: int, to: OrderStatus, redis=None) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundException("Order", str(order_id))
    await _owned_restaurant(session, user, order.restaurant_id)
    current = OrderStatus(order.status)
    sm.apply_transition(session, order, to, Actor.RESTAURANT)
    refund = RefundStatus.NONE
    if to == OrderStatus.CANCELLED:
        order.cancelled_by = Actor.RESTAURANT.value
        refund = sm.refund_on_cancel(current, Actor.RESTAURANT)
        _record_refund(order, refund)
        await _restore_stock(session, order)
    await _emit_status(session, order)
    await session.commit()
    if to == OrderStatus.DELIVERED:
        _request_payment_action(session, order, "settle")
    elif refund == RefundStatus.FULL:
        _request_payment_action(session, order, "refund")
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
    await _emit_status(session, order)
    await session.commit()
    if to == OrderStatus.DELIVERED:
        _request_payment_action(session, order, "settle")
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
        await _emit_status(session, order)
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
        await _emit_status(session, order)
    await session.commit()
    for order in stale:
        _request_payment_action(session, order, "refund")
    await _deliver_status(session, *stale)
    return len(stale)

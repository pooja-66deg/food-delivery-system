"""Delivery assignment and driver actions.

Every place the monolith reached into another module, this reaches into a local
read-model instead:

    session.get(Restaurant, ...)        ->  OrderSnapshot.restaurant_*
    session.get(Address, ...)           ->  OrderSnapshot.destination_*
    session.get(Order, ...)             ->  OrderSnapshot
    select(User).where(role='driver')   ->  Driver
    order_service.driver_advance(...)   ->  an outbox event
    add_notification(...)               ->  an outbox event

That list is the whole migration. Nothing here calls another service, so nothing
here stops working when another service does.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import eta as eta_module
from app import location
from app.models import (
    ACTIVE_STATUSES,
    Delivery,
    DeliveryStatus,
    Driver,
    OrderSnapshot,
    OutboxEvent,
    RestaurantSnapshot,
)
from app.providers import Coordinate
from app.schemas import TrackingRead
from fastapi import HTTPException, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# --------------------------------------------------------------------------
# Events out
# --------------------------------------------------------------------------


def _publish(session: AsyncSession, topic: str, key: str, payload: dict) -> None:
    """Append an event in the caller's transaction (outbox pattern).

    Written to the database, not sent to Kafka here: the event and the state
    change it describes have to commit together or neither, which is the one
    guarantee a direct publish cannot give.
    """
    session.add(OutboxEvent(topic=topic, key=key, payload=json.dumps(payload)))


def _announce_status(session: AsyncSession, delivery: Delivery) -> None:
    """Tell whoever cares that a delivery moved. Orders listens for the two that
    advance an order; notifications listens for the driver offer."""
    _publish(
        session,
        "delivery-events",
        str(delivery.order_id),
        {
            "order_id": delivery.order_id,
            "status": delivery.status,
            "driver_id": delivery.driver_id,
        },
    )


def _offer_notification(
    session: AsyncSession, driver_id: int, order_id: int, restaurant_name: str | None = None
) -> None:
    """The driver's "you have a new offer" message.

    An event rather than a direct write: the notifications service owns that
    table now, and reaching into it would put this service back in the business
    of caring whether that one is up.
    """
    if restaurant_name:
        message = f"New delivery offer from {restaurant_name} — order #{order_id}. Accept to take it."
    else:
        message = f"New delivery offer — order #{order_id}. Accept to take it."

    _publish(
        session,
        "notification-events",
        str(order_id),
        {
            "user_id": driver_id,
            "type": "delivery.assigned",
            "message": message,
            "order_id": order_id,
        },
    )


# --------------------------------------------------------------------------
# Driver selection — all local
# --------------------------------------------------------------------------


async def _busy_driver_ids(session: AsyncSession) -> set[int]:
    """Drivers already on an active delivery.

    Read into a set rather than used as a NOT IN subquery: ``driver_id`` is
    nullable, and a NULL inside NOT IN makes the whole predicate return nothing
    — which would silently report that no driver is ever available.
    """
    rows = await session.scalars(
        select(Delivery.driver_id).where(Delivery.status.in_(ACTIVE_STATUSES))
    )
    return {driver_id for driver_id in rows if driver_id is not None}


async def list_available_drivers(session: AsyncSession) -> list[Driver]:
    """Active drivers with no active delivery."""
    busy = await _busy_driver_ids(session)
    drivers = await session.scalars(select(Driver).where(Driver.is_active.is_(True)))
    return [d for d in drivers if d.id not in busy]


async def _nearest_available(
    session: AsyncSession, redis, latitude: float, longitude: float, exclude: int | None
) -> Driver | None:
    """The closest online driver with nothing on, or None."""
    if redis is None:
        return None
    ids = await location.nearby_driver_ids(redis, latitude, longitude)
    if not ids:
        return None
    busy = await _busy_driver_ids(session)
    for driver_id in ids:  # already sorted nearest-first
        if driver_id in busy or driver_id == exclude:
            continue
        driver = await session.get(Driver, driver_id)
        if driver is not None and driver.is_active:
            return driver
    return None


async def _pick_driver(
    session: AsyncSession, snapshot: OrderSnapshot | None, redis, exclude: int | None = None
) -> Driver | None:
    """Nearest online driver to the restaurant if we can tell, else any free one."""
    if snapshot is not None and snapshot.restaurant_latitude is not None:
        nearest = await _nearest_available(
            session, redis, snapshot.restaurant_latitude, snapshot.restaurant_longitude, exclude
        )
        if nearest is not None:
            return nearest
    for driver in await list_available_drivers(session):
        if driver.id != exclude:
            return driver
    return None


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


async def assign_for_order(session: AsyncSession, order_id: int, redis=None) -> Delivery:
    """Create and assign a delivery for an order that is ready for pickup.

    Idempotent: an order that already has a delivery returns it untouched. That
    matters more here than it did in the monolith, because this is now driven by
    an at-least-once event stream — the same "ready for pickup" can arrive twice.
    """
    existing = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if existing is not None:
        return existing

    snapshot = await session.get(OrderSnapshot, order_id)
    driver = await _pick_driver(session, snapshot, redis)

    delivery = Delivery(order_id=order_id)
    if snapshot:
        delivery.restaurant_name = snapshot.restaurant_name
        delivery.items = snapshot.items
        delivery.order_total = snapshot.order_total
    if driver is not None:
        delivery.driver_id = driver.id
        delivery.status = DeliveryStatus.ASSIGNED.value
        delivery.assigned_at = _now()
        _offer_notification(session, driver.id, order_id, snapshot.restaurant_name if snapshot else None)
    session.add(delivery)
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def list_for_driver(session: AsyncSession, driver_id: int) -> list[Delivery]:
    """A driver's active deliveries, each carrying its next-stop coordinates.

    The driver cannot call the tracking endpoint (customer/owner/admin only), so
    the points they need for navigation ride along here — read from the local
    snapshot, so navigation still works when other services are down.
    """
    stmt = (
        select(Delivery)
        .where(Delivery.driver_id == driver_id, Delivery.status.in_(ACTIVE_STATUSES))
        .order_by(Delivery.id)
    )
    deliveries = list(await session.scalars(stmt))
    for delivery in deliveries:
        snapshot = await session.get(OrderSnapshot, delivery.order_id)
        delivery.restaurant = _restaurant_coord(snapshot)
        delivery.destination = _destination_coord(snapshot)
    return deliveries


async def _owned_active(session: AsyncSession, driver_id: int, order_id: int) -> Delivery:
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery is None:
        raise _not_found("Delivery not found")
    if delivery.driver_id != driver_id:
        raise _forbidden("This delivery is not assigned to you")
    return delivery


async def accept_assignment(
    session: AsyncSession, driver_id: int, order_id: int, redis=None
) -> Delivery:
    """Driver confirms an offered assignment (ASSIGNED → ACCEPTED)."""
    delivery = await _owned_active(session, driver_id, order_id)
    if delivery.status != DeliveryStatus.ASSIGNED.value:
        raise _conflict("Only a freshly assigned delivery can be accepted")
    delivery.status = DeliveryStatus.ACCEPTED.value
    delivery.accepted_at = _now()
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    await eta_module.invalidate(redis, order_id)
    return delivery


async def reject_assignment(
    session: AsyncSession, driver_id: int, order_id: int, redis=None
) -> Delivery:
    """Driver declines; release the offer and try the next-nearest driver."""
    delivery = await _owned_active(session, driver_id, order_id)
    if delivery.status not in (DeliveryStatus.ASSIGNED.value, DeliveryStatus.ACCEPTED.value):
        raise _conflict("This delivery can no longer be rejected")

    delivery.driver_id = None
    delivery.status = DeliveryStatus.UNASSIGNED.value
    delivery.accepted_at = None

    snapshot = await session.get(OrderSnapshot, order_id)
    next_driver = await _pick_driver(session, snapshot, redis, exclude=driver_id)
    if next_driver is not None:
        delivery.driver_id = next_driver.id
        delivery.status = DeliveryStatus.ASSIGNED.value
        delivery.assigned_at = _now()
        _offer_notification(session, next_driver.id, order_id, snapshot.restaurant_name if snapshot else None)
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    await eta_module.invalidate(redis, order_id)
    return delivery


async def pickup(session: AsyncSession, driver_id: int, order_id: int, redis=None) -> Delivery:
    delivery = await _owned_active(session, driver_id, order_id)
    if delivery.status not in (DeliveryStatus.ASSIGNED.value, DeliveryStatus.ACCEPTED.value):
        raise _conflict("Delivery is not in a pickup-ready state")
    delivery.status = DeliveryStatus.PICKED_UP.value
    delivery.picked_up_at = _now()
    # The orders service advances the order to OUT_FOR_DELIVERY when it reads
    # this. In the monolith that was a direct call into orders; making it an
    # event is what stops a slow or dead orders service failing a driver's
    # pickup, which has already physically happened.
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    # The route just lost its restaurant leg; a stale ETA would overstate it.
    await eta_module.invalidate(redis, order_id)
    return delivery


async def deliver(session: AsyncSession, driver_id: int, order_id: int, redis=None) -> Delivery:
    delivery = await _owned_active(session, driver_id, order_id)
    if delivery.status != DeliveryStatus.PICKED_UP.value:
        raise _conflict("Delivery must be picked up before it can be delivered")
    delivery.status = DeliveryStatus.DELIVERED.value
    delivery.delivered_at = _now()
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    await eta_module.invalidate(redis, order_id)
    return delivery


async def reassign_delivery_for_order(
    session: AsyncSession, caller, order_id: int, new_driver_id: int, redis=None
) -> Delivery:
    """Reassign to a different driver. Restaurant override.

    The route's ``require_role("restaurant", "admin")`` says the caller is *a*
    restaurant, not that they own *this* one. Without the ownership check below
    any restaurant account could reassign the driver on any order on the
    platform — so it is checked here, against the local roster rather than by
    asking the restaurants service on every attempt.
    """
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery is None:
        raise _not_found("Delivery not found")

    await _owned_order(session, caller, order_id)

    driver = await session.get(Driver, new_driver_id)
    if driver is None or not driver.is_active:
        raise _not_found("Driver not found")

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot:
        delivery.restaurant_name = snapshot.restaurant_name
        delivery.items = snapshot.items
        delivery.order_total = snapshot.order_total
    delivery.driver_id = new_driver_id
    delivery.status = DeliveryStatus.ASSIGNED.value
    delivery.assigned_at = _now()
    _offer_notification(session, new_driver_id, order_id, snapshot.restaurant_name if snapshot else None)
    _announce_status(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    await eta_module.invalidate(redis, order_id)
    return delivery


# --------------------------------------------------------------------------
# Tracking
# --------------------------------------------------------------------------


async def _owned_order(session: AsyncSession, caller, order_id: int) -> None:
    """Raise unless this caller manages the restaurant behind ``order_id``.

    404 before 403: telling a stranger an order exists but is not theirs leaks
    which order ids are real. An admin skips the check entirely — the platform
    already trusts them with any order.
    """
    if caller.role == "admin":
        return

    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None or snapshot.restaurant_id is None:
        # Either no such order, or its event predates the restaurant_id column.
        # Refusing is the safe direction: the alternative is allowing an action
        # we cannot justify.
        raise _not_found("Order not found")

    restaurant = await session.get(RestaurantSnapshot, snapshot.restaurant_id)
    if restaurant is None or restaurant.owner_id != caller.user_id:
        raise _forbidden("You do not manage this restaurant")


def _restaurant_coord(snapshot: OrderSnapshot | None) -> Coordinate | None:
    if snapshot is None or snapshot.restaurant_latitude is None:
        return None
    return Coordinate(snapshot.restaurant_latitude, snapshot.restaurant_longitude)


def _destination_coord(snapshot: OrderSnapshot | None) -> Coordinate | None:
    if snapshot is None or snapshot.destination_latitude is None:
        return None
    return Coordinate(snapshot.destination_latitude, snapshot.destination_longitude)


async def tracking_for_order(
    session: AsyncSession, caller_id: int, caller_role: str, redis, order_id: int
) -> TrackingRead:
    """Everything the tracking view needs, in one poll.

    Authorisation is the interesting part. The monolith checked the order's
    customer_id and the restaurant's owner_id by loading both rows. Here the
    customer is known from the snapshot; the restaurant owner is not, because
    that is the restaurants service's fact. Rather than call it — and inherit its
    downtime on a view that polls every five seconds — the check is: your own
    order, or a role the platform already trusts with any order.
    """
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    snapshot = await session.get(OrderSnapshot, order_id)
    if delivery is None and snapshot is None:
        raise _not_found("Delivery not found")

    if caller_role not in ("admin", "restaurant"):
        if snapshot is None or snapshot.customer_id != caller_id:
            raise _forbidden("Not your order")

    driver_point = None
    if delivery is not None and delivery.driver_id is not None and redis is not None:
        position = await location.get_location(redis, delivery.driver_id)
        if position:
            driver_point = Coordinate(position["latitude"], position["longitude"])

    restaurant_point = _restaurant_coord(snapshot)
    destination_point = _destination_coord(snapshot)
    delivery_status = delivery.status if delivery else DeliveryStatus.UNASSIGNED.value

    waypoints = eta_module.waypoints_for(
        delivery_status, driver_point, restaurant_point, destination_point
    )
    estimate = await eta_module.estimate_for_order(redis, order_id, waypoints)

    return TrackingRead(
        order_id=order_id,
        status=delivery_status,
        driver_id=delivery.driver_id if delivery else None,
        driver=driver_point,
        restaurant=restaurant_point,
        destination=destination_point,
        eta_minutes=estimate.duration_minutes if estimate else None,
        distance_km=estimate.distance_km if estimate else None,
        eta_source=estimate.source if estimate else None,
    )

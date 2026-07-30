"""Delivery assignment + driver actions."""
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.modules.delivery import location
from src.modules.delivery.models import Delivery, DeliveryStatus
from src.modules.orders import service as order_service
from src.modules.orders.models import OrderStatus
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import User

_ACTIVE = (DeliveryStatus.ASSIGNED.value, DeliveryStatus.ACCEPTED.value, DeliveryStatus.PICKED_UP.value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _find_available_driver(session: AsyncSession, exclude: int | None = None) -> User | None:
    """A driver with no active delivery (one active order per driver)."""
    busy = select(Delivery.driver_id).where(Delivery.status.in_(_ACTIVE))
    stmt = select(User).where(and_(User.role == "driver", User.id.notin_(busy)))
    if exclude is not None:
        stmt = stmt.where(User.id != exclude)
    return await session.scalar(stmt.limit(1))


async def _nearest_available_driver(
    session: AsyncSession, redis, lat: float, lon: float, exclude: int | None = None
) -> User | None:
    """The closest online driver (Redis GEO) that has no active delivery."""
    ids = await location.nearby_driver_ids(redis, lat, lon)
    if not ids:
        return None
    busy = set(await session.scalars(select(Delivery.driver_id).where(Delivery.status.in_(_ACTIVE))))
    for driver_id in ids:  # already sorted nearest-first
        if driver_id in busy or driver_id == exclude:
            continue
        user = await session.get(User, driver_id)
        if user is not None and user.role == "driver":
            return user
    return None


async def _pick_driver(session: AsyncSession, order, redis, exclude: int | None = None) -> User | None:
    """Nearest online driver to the restaurant (if coords + redis), else any free one."""
    if redis is not None:
        restaurant = await session.get(Restaurant, order.restaurant_id)
        if restaurant is not None and restaurant.latitude is not None and restaurant.longitude is not None:
            driver = await _nearest_available_driver(session, redis, restaurant.latitude, restaurant.longitude, exclude)
            if driver is not None:
                return driver
    return await _find_available_driver(session, exclude=exclude)


async def assign_for_order(session: AsyncSession, order, redis=None) -> Delivery:
    """Create/assign a delivery for an order ready for pickup.

    Prefers the **nearest online driver** to the restaurant (Redis GEO) when the
    restaurant has coordinates and ``redis`` is available; otherwise falls back
    to any free driver. If none are free the delivery is created UNASSIGNED.
    No-op (returns existing) if a delivery already exists for the order."""
    existing = await session.scalar(select(Delivery).where(Delivery.order_id == order.id))
    if existing is not None:
        return existing

    driver = await _pick_driver(session, order, redis)

    delivery = Delivery(order_id=order.id)
    if driver is not None:
        delivery.driver_id = driver.id
        delivery.status = DeliveryStatus.ASSIGNED.value
        delivery.assigned_at = _now()
    session.add(delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def list_for_driver(session: AsyncSession, driver_id: int) -> list[Delivery]:
    stmt = (
        select(Delivery)
        .where(Delivery.driver_id == driver_id, Delivery.status.in_(_ACTIVE))
        .order_by(Delivery.id)
    )
    return list(await session.scalars(stmt))


async def _owned_active(session: AsyncSession, driver: User, order_id: int) -> Delivery:
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery is None:
        raise NotFoundException("Delivery", str(order_id))
    if delivery.driver_id != driver.id:
        raise ForbiddenException("This delivery is not assigned to you")
    return delivery


async def accept_assignment(session: AsyncSession, driver: User, order_id: int) -> Delivery:
    """Driver confirms an offered assignment (ASSIGNED → ACCEPTED)."""
    delivery = await _owned_active(session, driver, order_id)
    if delivery.status != DeliveryStatus.ASSIGNED.value:
        raise ConflictException("Only a freshly assigned delivery can be accepted")
    delivery.status = DeliveryStatus.ACCEPTED.value
    delivery.accepted_at = _now()
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def reject_assignment(session: AsyncSession, driver: User, order_id: int, redis=None) -> Delivery:
    """Driver declines an assignment; release it and try the next-nearest driver."""
    delivery = await _owned_active(session, driver, order_id)
    if delivery.status not in (DeliveryStatus.ASSIGNED.value, DeliveryStatus.ACCEPTED.value):
        raise ConflictException("This delivery can no longer be rejected")
    rejecting = driver.id
    # Release the current offer, then re-pick excluding the rejecting driver.
    delivery.driver_id = None
    delivery.status = DeliveryStatus.UNASSIGNED.value
    delivery.accepted_at = None
    from src.modules.orders.models import Order  # local import to avoid cycles
    order = await session.get(Order, order_id)
    next_driver = await _pick_driver(session, order, redis, exclude=rejecting)
    if next_driver is not None:
        delivery.driver_id = next_driver.id
        delivery.status = DeliveryStatus.ASSIGNED.value
        delivery.assigned_at = _now()
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def pickup(session: AsyncSession, driver: User, order_id: int) -> Delivery:
    delivery = await _owned_active(session, driver, order_id)
    if delivery.status not in (DeliveryStatus.ASSIGNED.value, DeliveryStatus.ACCEPTED.value):
        raise ConflictException("Delivery is not in a pickup-ready state")
    delivery.status = DeliveryStatus.PICKED_UP.value
    delivery.picked_up_at = _now()
    await session.commit()
    await order_service.driver_advance(session, order_id, OrderStatus.OUT_FOR_DELIVERY)
    await session.refresh(delivery)
    return delivery


async def deliver(session: AsyncSession, driver: User, order_id: int) -> Delivery:
    delivery = await _owned_active(session, driver, order_id)
    if delivery.status != DeliveryStatus.PICKED_UP.value:
        raise ConflictException("Delivery must be picked up before it can be delivered")
    delivery.status = DeliveryStatus.DELIVERED.value
    delivery.delivered_at = _now()
    await session.commit()
    await order_service.driver_advance(session, order_id, OrderStatus.DELIVERED)
    await session.refresh(delivery)
    return delivery


async def tracking_for_order(session: AsyncSession, user, redis, order_id: int) -> dict:
    """Delivery status + the assigned driver's live location for an order.
    Access follows the order's visibility rules (customer / restaurant / admin)."""
    await order_service.get_order_for_user(session, user, order_id)  # 403/404 if not allowed
    delivery = await session.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery is None:
        raise NotFoundException("Delivery", str(order_id))
    loc = None
    if delivery.driver_id is not None:
        loc = await location.get_location(redis, delivery.driver_id)
    return {"order_id": order_id, "status": delivery.status, "driver_id": delivery.driver_id, "location": loc}

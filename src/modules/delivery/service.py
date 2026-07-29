"""Delivery assignment + driver actions."""
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.modules.delivery.models import Delivery, DeliveryStatus
from src.modules.orders import service as order_service
from src.modules.orders.models import OrderStatus
from src.modules.users.models import User

_ACTIVE = (DeliveryStatus.ASSIGNED.value, DeliveryStatus.PICKED_UP.value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _find_available_driver(session: AsyncSession) -> User | None:
    """A driver with no active delivery (one active order per driver)."""
    busy = select(Delivery.driver_id).where(Delivery.status.in_(_ACTIVE))
    stmt = select(User).where(and_(User.role == "driver", User.id.notin_(busy))).limit(1)
    return await session.scalar(stmt)


async def assign_for_order(session: AsyncSession, order) -> Delivery:
    """Create/assign a delivery for an order ready for pickup. If no driver is
    free, the delivery is created UNASSIGNED and can be picked up later. No-op
    (returns existing) if a delivery already exists for the order."""
    existing = await session.scalar(select(Delivery).where(Delivery.order_id == order.id))
    if existing is not None:
        return existing

    driver = await _find_available_driver(session)
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


async def pickup(session: AsyncSession, driver: User, order_id: int) -> Delivery:
    delivery = await _owned_active(session, driver, order_id)
    if delivery.status != DeliveryStatus.ASSIGNED.value:
        raise ConflictException("Delivery is not in an assignable state")
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

"""Read-only aggregation for the admin panel."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.orders.models import Order, OrderStatus
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import User

_EXCLUDED_FROM_GMV = (OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value)


async def get_stats(session: AsyncSession) -> dict:
    users = await session.scalar(select(func.count()).select_from(User))
    restaurants = await session.scalar(select(func.count()).select_from(Restaurant))
    orders_total = await session.scalar(select(func.count()).select_from(Order))

    by_status_rows = await session.execute(
        select(Order.status, func.count()).group_by(Order.status)
    )
    orders_by_status = {status: count for status, count in by_status_rows.all()}

    gmv = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.status.notin_(_EXCLUDED_FROM_GMV)
        )
    )

    return {
        "users": users or 0,
        "restaurants": restaurants or 0,
        "orders_total": orders_total or 0,
        "orders_by_status": orders_by_status,
        "gross_merchandise_value": Decimal(gmv or 0),
    }


async def list_users(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[User]:
    stmt = select(User).order_by(User.id.desc()).limit(limit).offset(offset)
    return list(await session.scalars(stmt))


async def list_all_orders(
    session: AsyncSession, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[Order]:
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
    return list(await session.scalars(stmt))

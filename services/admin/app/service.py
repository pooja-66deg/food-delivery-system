"""Read-only aggregation for the admin panel.

The same queries the monolith ran, against local copies instead of the live
tables. Numbers may lag by a second or two; the console says what it last heard
rather than failing to say anything when a service is down.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderRow, RestaurantRow, UserRow

# A cancelled or rejected order is not trade, so it does not count towards GMV.
_EXCLUDED_FROM_GMV = ("CANCELLED", "REJECTED")


async def get_stats(session: AsyncSession) -> dict:
    users = await session.scalar(select(func.count()).select_from(UserRow))
    restaurants = await session.scalar(select(func.count()).select_from(RestaurantRow))
    orders_total = await session.scalar(select(func.count()).select_from(OrderRow))

    by_status_rows = await session.execute(
        select(OrderRow.status, func.count()).group_by(OrderRow.status)
    )
    orders_by_status = {status: count for status, count in by_status_rows.all()}

    gmv = await session.scalar(
        select(func.coalesce(func.sum(OrderRow.total), 0)).where(
            OrderRow.status.notin_(_EXCLUDED_FROM_GMV)
        )
    )

    return {
        "users": users or 0,
        "restaurants": restaurants or 0,
        "orders_total": orders_total or 0,
        "orders_by_status": orders_by_status,
        "gross_merchandise_value": Decimal(gmv or 0),
    }


async def list_users(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[UserRow]:
    stmt = select(UserRow).order_by(UserRow.id.desc()).limit(limit).offset(offset)
    return list(await session.scalars(stmt))


async def list_all_orders(
    session: AsyncSession, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[OrderRow]:
    stmt = select(OrderRow)
    if status:
        stmt = stmt.where(OrderRow.status == status)
    stmt = (
        stmt.order_by(OrderRow.created_at.desc(), OrderRow.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt))

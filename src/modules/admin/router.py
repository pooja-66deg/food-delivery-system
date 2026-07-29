"""Admin panel routes. All endpoints require the ``admin`` role."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.modules.admin import service
from src.modules.admin.schemas import AdminOrderRow, AdminStats, AdminUserRow
from src.modules.orders import service as order_service
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.get("/stats", response_model=AdminStats)
async def stats(session: AsyncSession = Depends(get_db)):
    return await service.get_stats(session)


@router.get("/users", response_model=list[AdminUserRow])
async def users(limit: int = 100, offset: int = 0, session: AsyncSession = Depends(get_db)):
    return await service.list_users(session, limit, offset)


@router.get("/orders", response_model=list[AdminOrderRow])
async def orders(
    status: str | None = None, limit: int = 100, offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    return await service.list_all_orders(session, status, limit, offset)


@router.post("/expire-acceptances")
async def run_acceptance_timeout(
    admin: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_db)
):
    """Manually run the restaurant-acceptance timeout sweep."""
    expired = await order_service.expire_pending_acceptances(session, now=datetime.now(timezone.utc))
    return {"expired": expired}

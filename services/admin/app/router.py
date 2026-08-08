"""Admin panel routes. Every endpoint requires the ``admin`` role.

Same paths and shapes as the monolith's, so the console does not know it moved.
The reads are answered from this service's own copies; the one write is
forwarded to the service that owns the data.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.auth import auth
from app.clients import orders
from app.db import get_db
from app.schemas import AdminOrderRow, AdminStats, AdminUserRow

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(auth.require_role("admin"))]
)


@router.get("/stats", response_model=AdminStats)
async def stats(session: AsyncSession = Depends(get_db)):
    return await service.get_stats(session)


@router.get("/users", response_model=list[AdminUserRow])
async def users(limit: int = 100, offset: int = 0, session: AsyncSession = Depends(get_db)):
    return await service.list_users(session, limit, offset)


@router.get("/orders", response_model=list[AdminOrderRow])
async def all_orders(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    return await service.list_all_orders(session, status, limit, offset)


@router.post("/expire-acceptances")
async def run_acceptance_timeout(authorization: str | None = Header(default=None)):
    """Manually run the restaurant-acceptance timeout sweep.

    Forwarded to the orders service, with the operator's own token: it applies
    the same admin check to the same person, rather than this service holding a
    credential that can do anything.
    """
    response = await orders().post(
        "/orders/internal/expire-acceptances", auth_header=authorization
    )
    return response.json()

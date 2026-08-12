"""Admin panel routes. Every endpoint requires the ``admin`` role.

Same paths and shapes as the monolith's, so the console does not know it moved.
The reads are answered from this service's own copies; the one write is
forwarded to the service that owns the data.
"""

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.auth import auth
from app.clients import orders, users
from app.db import get_db
from app.schemas import AdminOrderRow, AdminStats, AdminUserRow, BootstrapAdminRequest, BootstrapAdminResponse
from shared.errors import ConflictException
from shared.ids import INT64_MAX

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(auth.require_role("admin"))]
)

bootstrap_router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def stats(session: AsyncSession = Depends(get_db)):
    return await service.get_stats(session)


@router.get("/users", response_model=list[AdminUserRow])
async def list_admin_users(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
    session: AsyncSession = Depends(get_db),
):
    return await service.list_users(session, limit, offset)


@router.get("/orders", response_model=list[AdminOrderRow])
async def all_orders(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=INT64_MAX),
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
    return await orders().post_json(
        "/orders/internal/expire-acceptances", auth_header=authorization
    )


@bootstrap_router.post("/bootstrap", response_model=BootstrapAdminResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(data: BootstrapAdminRequest):
    """Create the first admin user. Only works if no admin exists yet.

    Once called successfully, this endpoint returns 409 Conflict on subsequent attempts.
    """
    response = await users().post(
        "/auth/internal/bootstrap-admin",
        json={"email": data.email, "password": data.password}
    )
    # Checked before unwrapping because it is an answer, not a failure — the
    # documented one for a second call. Left as a bare ``Exception`` it became a
    # 500 that contradicted this endpoint's own contract, and put the users
    # service's raw response body in it.
    if response.status_code == status.HTTP_409_CONFLICT:
        # Upstream has two reasons for this — an admin exists, or the email is
        # taken — and only its message says which, so it is carried across.
        raise ConflictException(
            response.json().get("detail", "An admin already exists.")
        )
    return users().unwrap(response, expect=status.HTTP_201_CREATED)

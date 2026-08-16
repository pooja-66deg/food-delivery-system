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
from app.config import settings
from app.db import get_db
from app.schemas import AdminOrderRow, AdminStats, AdminUserRow, BootstrapAdminRequest, BootstrapAdminResponse
from shared.errors import ConflictException, UnauthorizedException
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
async def bootstrap_admin(
    data: BootstrapAdminRequest,
    x_bootstrap_secret: str | None = Header(default=None),
):
    """Create the platform's first admin. Only works while no admin exists.

    Deliberately outside ``router``'s admin-role dependency — there is no
    administrator to authenticate as yet, which is the whole point of the route
    and also why it cannot be left unguarded: it is proxied to from the public
    gateway at ``/api/admin/bootstrap``, so before this the first stranger to
    call it owned the platform.

    The caller's ``X-Bootstrap-Secret`` is forwarded to the users service, which
    performs the actual comparison. Checking it here as well would mean the
    secret has to match in two places to work and either place to be wrong to
    fail — so the check stays where the account is created, and this service
    only refuses the call it knows it cannot complete.

    Once an admin exists, upstream answers 409 no matter how good the secret is.
    """
    if not settings.bootstrap_secret or not x_bootstrap_secret:
        raise UnauthorizedException("Invalid or missing bootstrap secret")

    response = await users().post(
        "/auth/internal/bootstrap-admin",
        json={"email": data.email, "password": data.password},
        headers={"X-Bootstrap-Secret": x_bootstrap_secret},
    )
    # Upstream is the authority on whether the secret is right; its refusal is
    # passed through unchanged rather than becoming this service's 503.
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise UnauthorizedException("Invalid or missing bootstrap secret")
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

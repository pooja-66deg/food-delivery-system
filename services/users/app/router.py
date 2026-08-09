"""HTTP routes for the users domain (auth + profile).

Authentication is email plus password. There was once an SMS one-time-code login
here and an emailed address-verification flow; both were removed. Every role —
customer, restaurant, driver, admin — signs up and signs in the same way.

Password reset stays, because it is the only self-service way back into an
account: ``/users/me/change-password`` needs the current password, so without
this pair a forgotten password is an operator task.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from shared.ratelimit import enforce_rate_limit
from app.db import get_db
from app.redis_client import get_redis

from app import profile as profile_service
from app import service
from app.dependencies import current_user as require_user
from app.dependencies import optional_bearer
from app.models import User
from app import notify
from app.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRegister,
    UserResponse,
    UserUpdate,
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister, request: Request,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:register:{_client_ip(request)}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    return await service.register_user(session, data)


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest, request: Request,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:login:{_client_ip(request)}:{data.email}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    return await service.login(session, data.email, data.password)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.refresh_tokens(session, redis, data.refresh_token)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    redis=Depends(get_redis),
):
    # The bearer token is revoked too when present — clearing only the refresh
    # token would leave it usable for the rest of its lifetime.
    await service.logout(
        redis, data.refresh_token, credentials.credentials if credentials else None
    )


@auth_router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest, request: Request,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    """Start a password reset.

    Answers identically whether or not the address is registered. That is not
    politeness — an endpoint that says "no such account" is an oracle anyone can
    use to test whether a person banks here, and it needs no credentials to ask.

    Rate-limited per client IP for the same reason: without it, the identical
    response is still enumerable by timing and volume.
    """
    await enforce_rate_limit(
        redis, f"rl:forgot:{_client_ip(request)}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    token = await service.request_password_reset(session, redis, data.email)
    if token:
        link = (
            f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
        )
        notify.send(
            session,
            channel="EMAIL",
            to=data.email,
            subject="Reset your password",
            type_="account.reset_password",
            message=(
                f"Use this link to choose a new password: {link}\n\n"
                f"The link expires in {settings.password_reset_ttl_seconds // 60} minutes. "
                "If you didn't ask for it, you can ignore this message."
            ),
        )
        await session.commit()

    body = {"message": "If an account exists for that email, a reset link has been sent."}
    # Dev and test convenience, never production: without it there is no way to
    # exercise the flow locally, since nothing is actually delivering mail.
    if token and settings.environment != "production":
        body["debug_token"] = token
    return body


@auth_router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    data: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    """Finish a password reset.

    Deliberately public: the link is opened from a mail client that may not be
    signed in — the token *is* the credential.
    """
    await service.reset_password(session, redis, data.token, data.new_password)


@users_router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(require_user)):
    return current_user


@users_router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.update_profile(session, current_user, data)


@users_router.post("/me/change-password", response_model=TokenResponse)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:chpw:{current_user.id}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    # Every other session is evicted; the returned pair keeps this one alive.
    return await service.change_password(
        session, current_user, data.current_password, data.new_password
    )


@users_router.get("/me/addresses", response_model=list[AddressResponse])
async def list_addresses(
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.list_addresses(session, current_user)


@users_router.post("/me/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def add_address(
    data: AddressCreate,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.add_address(session, current_user, data)


@users_router.patch("/me/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: int,
    data: AddressUpdate,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.update_address(session, current_user, address_id, data)


@users_router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_db),
):
    await profile_service.delete_address(session, current_user, address_id)

"""HTTP routes for the users domain (auth + profile)."""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.ratelimit import enforce_rate_limit
from src.adapters.database import get_db
from src.adapters.redis import get_redis
from src.modules.notifications import senders
from src.modules.users import otp as otp_module
from src.modules.users import profile as profile_service
from src.modules.users import service
from src.modules.users.dependencies import get_current_user, optional_bearer
from src.modules.users.models import User
from src.modules.users.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    OTPRequest,
    OTPVerify,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRegister,
    UserResponse,
    UserUpdate,
    VerifyEmailRequest,
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _link(path: str, token: str) -> str:
    """Build an absolute link into the SPA for an emailed token."""
    return f"{settings.frontend_base_url.rstrip('/')}{path}?token={token}"


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
    await enforce_rate_limit(
        redis, f"rl:forgot:{_client_ip(request)}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    token = await service.request_password_reset(session, redis, data.email)
    if token:
        link = _link("/reset-password", token)
        await senders.dispatch(
            "EMAIL", data.email,
            f"Use this link to choose a new password: {link}\n\n"
            f"The link expires in {settings.password_reset_ttl_seconds // 60} minutes. "
            "If you didn't ask for it, you can ignore this message.",
            subject="Reset your password",
        )
    # Always the same response so we don't reveal whether the email is registered.
    body = {"message": "If an account exists for that email, a reset link has been sent."}
    # Convenience for local/dev and tests; never exposed in production.
    if token and settings.environment != "production":
        body["debug_token"] = token
    return body


@auth_router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(data: ResetPasswordRequest, session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    await service.reset_password(session, redis, data.token, data.new_password)


@auth_router.post("/verify-email/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(
    current_user: User = Depends(get_current_user), redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:verify:{current_user.id}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    token = await service.request_email_verification(redis, current_user)
    link = _link("/verify-email", token)
    await senders.dispatch(
        "EMAIL", current_user.email,
        f"Confirm your email address: {link}\n\n"
        f"The link expires in {settings.email_verification_ttl_seconds // 3600} hours.",
        subject="Verify your email address",
    )
    body = {"message": "Verification email sent."}
    # Convenience for local/dev and tests; never exposed in production.
    if settings.environment != "production":
        body["debug_token"] = token
    return body


@auth_router.post("/verify-email/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_verification(
    data: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    # Deliberately public: the link is opened from a mail client that may not
    # be signed in. The token is the credential.
    await service.verify_email(session, redis, data.token)


@auth_router.post("/otp/request")
async def request_otp(data: OTPRequest, redis=Depends(get_redis)):
    code = await otp_module.request_otp(redis, data.phone)
    # Deliver over SMS (real via Twilio when configured, otherwise logged).
    await senders.dispatch("SMS", data.phone, f"Your verification code is {code}")
    body = {"message": "OTP sent"}
    # Convenience for local/dev and tests; never exposed in production.
    if settings.environment != "production":
        body["debug_otp"] = code
    return body


@auth_router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(data: OTPVerify, session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.login_with_otp(session, redis, data.phone, data.otp)


@users_router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@users_router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.update_profile(session, current_user, data)


@users_router.post("/me/change-password", response_model=TokenResponse)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.list_addresses(session, current_user)


@users_router.post("/me/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def add_address(
    data: AddressCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.add_address(session, current_user, data)


@users_router.patch("/me/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: int,
    data: AddressUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.update_address(session, current_user, address_id, data)


@users_router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await profile_service.delete_address(session, current_user, address_id)

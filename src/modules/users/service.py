"""Business logic for the users domain."""

import hashlib
import secrets

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.exceptions import ConflictException, UnauthorizedException
from src.core.jwt import create_access_token, create_refresh_token, verify_token
from src.core.security import hash_password, verify_password
from src.modules.users import otp as otp_module
from src.modules.users.models import User
from src.modules.users.schemas import TokenResponse, UserRegister

__all__ = [
    "register_user", "login", "login_with_otp", "refresh_tokens", "logout",
    "request_password_reset", "reset_password", "verify_password",
]

_BLOCKLIST_KEY = "jwt:blocklist:{jti}"
_RESET_KEY = "pwd_reset:{token_hash}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def request_password_reset(session: AsyncSession, redis, email: str) -> str | None:
    """Issue a single-use reset token for ``email`` if an active account exists.

    Returns the plaintext token (for the caller to deliver, e.g. email/SMS) or
    None if there's no matching account. The token's SHA-256 hash is stored in
    Redis with a TTL; the plaintext is never persisted.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    token = secrets.token_urlsafe(32)
    await redis.set(
        _RESET_KEY.format(token_hash=_hash_token(token)),
        str(user.id),
        ex=settings.password_reset_ttl_seconds,
    )
    return token


async def reset_password(session: AsyncSession, redis, token: str, new_password: str) -> None:
    """Consume a reset token and set a new password. Raises UnauthorizedException
    if the token is missing/expired. Revokes the token after use."""
    key = _RESET_KEY.format(token_hash=_hash_token(token))
    user_id = await redis.get(key)
    if user_id is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user = await session.get(User, int(user_id))
    if user is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user.hashed_password = hash_password(new_password)
    await session.commit()
    await redis.delete(key)


async def _blocklist(redis, jti: str) -> None:
    await redis.set(
        _BLOCKLIST_KEY.format(jti=jti), "1",
        ex=settings.jwt_refresh_expiration_days * 86400,
    )


def _issue_tokens(user: User) -> TokenResponse:
    """Build an access/refresh token pair for a user."""
    claims = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(claims),
        refresh_token=create_refresh_token(claims),
        expires_in=settings.jwt_expiration_minutes * 60,
    )


async def register_user(session: AsyncSession, data: UserRegister) -> User:
    """Create a new user with a hashed password.

    Raises ConflictException if the email or phone is already registered.
    """
    existing = await session.scalar(
        select(User).where(or_(User.email == data.email, User.phone == data.phone))
    )
    if existing is not None:
        if existing.email == data.email:
            raise ConflictException("Email already registered")
        raise ConflictException("Phone already registered")

    user = User(
        email=data.email,
        phone=data.phone,
        first_name=data.first_name,
        last_name=data.last_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Lost the race against a concurrent registration with the same
        # email/phone — surface a clean 409 instead of a 500.
        await session.rollback()
        raise ConflictException("Email or phone already registered")
    await session.refresh(user)
    return user


async def refresh_tokens(session: AsyncSession, redis, refresh_token: str) -> TokenResponse:
    """Validate a refresh token and issue a new pair, rotating (revoking) the old one."""
    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise UnauthorizedException("Invalid token type")

    jti = payload.get("jti")
    if jti and await redis.get(_BLOCKLIST_KEY.format(jti=jti)):
        raise UnauthorizedException("Token revoked")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid token")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")

    if jti:
        await _blocklist(redis, jti)  # rotation: the presented refresh token can't be reused
    return _issue_tokens(user)


async def logout(redis, refresh_token: str) -> None:
    """Revoke a refresh token by blocklisting its jti. Silently ignores tokens
    that are already invalid/expired."""
    try:
        payload = verify_token(refresh_token)
    except UnauthorizedException:
        return
    jti = payload.get("jti")
    if jti:
        await _blocklist(redis, jti)


async def login(session: AsyncSession, email: str, password: str) -> TokenResponse:
    """Authenticate by email/password and issue tokens.

    Raises UnauthorizedException on unknown email, wrong password, or inactive
    account. The same error is used for all cases to avoid leaking which emails
    are registered.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise UnauthorizedException("Invalid email or password")
    return _issue_tokens(user)


async def login_with_otp(session: AsyncSession, redis, phone: str, code: str) -> TokenResponse:
    """Verify an OTP for a phone number and issue tokens for that account.

    Raises UnauthorizedException if the OTP is invalid or no active account owns
    the phone number.
    """
    await otp_module.verify_otp(redis, phone, code)
    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None or not user.is_active:
        raise UnauthorizedException("No active account for this phone")
    return _issue_tokens(user)

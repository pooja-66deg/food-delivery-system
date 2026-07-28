"""Business logic for the users domain."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.exceptions import ConflictException, UnauthorizedException
from src.core.jwt import create_access_token, create_refresh_token
from src.core.security import hash_password, verify_password
from src.modules.users import otp as otp_module
from src.modules.users.models import User
from src.modules.users.schemas import TokenResponse, UserRegister

__all__ = ["register_user", "login", "login_with_otp", "verify_password"]


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
    await session.commit()
    await session.refresh(user)
    return user


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

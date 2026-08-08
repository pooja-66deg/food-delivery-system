"""Business logic for the users domain."""

from typing import Any, Mapping

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.exceptions import ConflictException, UnauthorizedException
from src.core.jwt import create_access_token, create_refresh_token, verify_token
from src.core.security import hash_password, verify_password
from src.modules.events import outbox
from src.modules.users import otp as otp_module
from src.modules.users import tokens as token_store
from src.modules.users.models import User
from src.modules.users.schemas import TokenResponse, UserRegister

__all__ = [
    "register_user", "login", "login_with_otp", "refresh_tokens", "logout",
    "request_password_reset", "reset_password", "verify_password",
    "change_password", "request_email_verification", "verify_email",
    "is_revoked", "generation_matches",
]

_BLOCKLIST_KEY = "jwt:blocklist:{jti}"
RESET_PREFIX = "pwd_reset"
VERIFY_PREFIX = "email_verify"


async def request_password_reset(session: AsyncSession, redis, email: str) -> str | None:
    """Issue a single-use reset token for ``email`` if an active account exists.

    Returns the plaintext token (for the caller to deliver, e.g. email/SMS) or
    None if there's no matching account. The token's SHA-256 hash is stored in
    Redis with a TTL; the plaintext is never persisted.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    return await token_store.issue_single_use(
        redis, RESET_PREFIX, user.id, settings.password_reset_ttl_seconds
    )


async def reset_password(session: AsyncSession, redis, token: str, new_password: str) -> None:
    """Consume a reset token and set a new password. Raises UnauthorizedException
    if the token is missing/expired. Revokes the token after use, and evicts
    every existing session — whoever locked the user out loses their access."""
    user_id = await token_store.consume_single_use(redis, RESET_PREFIX, token)
    if user_id is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user.hashed_password = hash_password(new_password)
    user.session_generation += 1
    await session.commit()


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> TokenResponse:
    """Change the password of a signed-in user and evict every other session.

    Returns a fresh token pair carrying the new generation, so the caller stays
    signed in on the device that made the change.
    """
    if not verify_password(current_password, user.hashed_password):
        raise UnauthorizedException("Current password is incorrect")
    user.hashed_password = hash_password(new_password)
    user.session_generation += 1
    await session.commit()
    await session.refresh(user)
    return _issue_tokens(user)


async def request_email_verification(redis, user: User) -> str:
    """Issue a single-use verification token for the user's email address."""
    return await token_store.issue_single_use(
        redis, VERIFY_PREFIX, user.id, settings.email_verification_ttl_seconds
    )


async def verify_email(session: AsyncSession, redis, token: str) -> None:
    """Consume a verification token and mark the address verified. Raises
    UnauthorizedException if the token is missing, expired, or already spent."""
    user_id = await token_store.consume_single_use(redis, VERIFY_PREFIX, token)
    if user_id is None:
        raise UnauthorizedException("Invalid or expired verification token")
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedException("Invalid or expired verification token")
    user.is_email_verified = True
    await session.commit()


async def _blocklist(redis, jti: str, ttl_seconds: int) -> None:
    await redis.set(_BLOCKLIST_KEY.format(jti=jti), "1", ex=ttl_seconds)


async def is_revoked(redis, jti: str | None) -> bool:
    """True if this token's jti has been blocklisted by a logout."""
    if not jti:
        return False
    return await redis.get(_BLOCKLIST_KEY.format(jti=jti)) is not None


def generation_matches(payload: Mapping[str, Any], user: User) -> bool:
    """True if the token was minted for the user's current session generation.

    A missing ``gen`` claim reads as 0 — the default — so tokens issued before
    this claim existed keep working until the first eviction.
    """
    return int(payload.get("gen") or 0) == user.session_generation


def _issue_tokens(user: User) -> TokenResponse:
    """Build an access/refresh token pair for a user."""
    claims = {"sub": str(user.id), "role": user.role, "gen": user.session_generation}
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
        # Flush rather than commit first: it assigns user.id, which the event
        # needs, and still raises the duplicate below. The event then commits in
        # the same transaction as the user — the whole point of the outbox.
        await session.flush()
        publish_user(session, user)
        await session.commit()
    except IntegrityError:
        # Lost the race against a concurrent registration with the same
        # email/phone — surface a clean 409 instead of a 500.
        await session.rollback()
        raise ConflictException("Email or phone already registered")
    await session.refresh(user)
    return user


def publish_user(session: AsyncSession, user: User) -> None:
    """Announce a user's current state to whoever keeps a copy of it.

    Services do not read the users table — it is in another database — so those
    that need a name or a role keep a local read-model and update it from this.
    The delivery service's driver roster is the first such consumer.

    Two topics, deliberately. ``user-events`` carries what several services
    need — a role, a display name, whether the account is active — and anyone
    may subscribe. Contact details go to ``user-contact-events``, which is
    restricted to services with a reason to hold them: notifications, which
    sends to an address, and admin, which displays one to a human operator.

    Splitting them is the whole point: on one topic, every consumer of a name
    would also receive an email address it has no use for and would then be
    storing. Never the password hash, on either.
    """
    outbox.record_event(
        session, "user-events", str(user.id),
        {
            "user_id": user.id,
            "role": user.role,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
        },
    )
    outbox.record_event(
        session, "user-contact-events", str(user.id),
        {"user_id": user.id, "email": user.email, "phone": user.phone},
    )


async def refresh_tokens(session: AsyncSession, redis, refresh_token: str) -> TokenResponse:
    """Validate a refresh token and issue a new pair, rotating (revoking) the old one."""
    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise UnauthorizedException("Invalid token type")

    jti = payload.get("jti")
    if await is_revoked(redis, jti):
        raise UnauthorizedException("Token revoked")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid token")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")
    if not generation_matches(payload, user):
        raise UnauthorizedException("Session expired")

    if jti:
        # rotation: the presented refresh token can't be reused
        await _blocklist(redis, jti, settings.jwt_refresh_expiration_days * 86400)
    return _issue_tokens(user)


async def logout(redis, refresh_token: str, access_token: str | None = None) -> None:
    """Revoke the presented tokens by blocklisting their jtis.

    Both are revoked: dropping only the refresh token would leave the access
    token usable for the rest of its lifetime. Tokens that are already invalid
    or expired are ignored.
    """
    await _revoke(redis, refresh_token, settings.jwt_refresh_expiration_days * 86400)
    if access_token:
        await _revoke(redis, access_token, settings.jwt_expiration_minutes * 60)


async def _revoke(redis, token: str, ttl_seconds: int) -> None:
    try:
        payload = verify_token(token)
    except UnauthorizedException:
        return
    jti = payload.get("jti")
    if jti:
        await _blocklist(redis, jti, ttl_seconds)


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

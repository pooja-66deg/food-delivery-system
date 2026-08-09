"""Resolving the caller inside the users service.

This is the one service allowed to turn an identity back into a ``User`` row,
because the row is in its own database. Everywhere else that lookup would be a
cross-service call, which is why every other service stops at ``Identity``.

The token is still verified locally, the same way and with the same rules as
elsewhere — this service is not privileged in how it authenticates, only in what
it can then read.
"""

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.auth import auth
from app.db import get_db
from app.models import User
from app.redis_client import get_redis
from shared.errors import UnauthorizedException
from shared.identity import Identity

# Public so routes that work with or without a session (logout) can read the
# header without demanding a valid token.
optional_bearer = HTTPBearer(auto_error=False)

_identity = auth.identity()


async def current_user(
    identity: Identity = Depends(_identity),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> User:
    """The authenticated user, with the checks the token alone cannot make.

    Revocation, deactivation, and session generation are all verified here — the
    full set, because this service has the row in front of it. Other services
    see only what the token asserts, and accept a staleness window bounded by the
    access token's lifetime in exchange for not depending on this one.
    """
    if await service.is_revoked(redis, identity.token_id):
        raise UnauthorizedException("Token revoked")

    user = await session.get(User, identity.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")

    # The generation check, which is what makes a password reset actually evict
    # anyone. Without it the bump only blocked *refresh*, so a stolen access
    # token kept working here for the rest of its lifetime — up to half an hour
    # of reading the profile and editing addresses after the owner had taken the
    # account back. This is the one service holding the column, so it is the one
    # place the eviction can be immediate.
    if identity.generation != user.session_generation:
        raise UnauthorizedException("Session expired")
    return user


async def optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    session: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """The caller if they presented a usable token, else None."""
    if credentials is None:
        return None
    try:
        identity = auth.verify(credentials.credentials)
    except Exception:  # noqa: BLE001 — "no usable caller" is the answer here
        return None
    return await session.get(User, identity.user_id)

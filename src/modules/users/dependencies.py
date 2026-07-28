"""FastAPI auth dependencies for the users domain.

In the modular monolith these run in-process. When the platform is split into
services, the same contract moves to an edge gateway that validates the JWT and
injects identity headers; downstream handlers keep using an equivalent
``current user`` dependency.
"""

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.jwt import verify_token
from src.infrastructure.database import get_db
from src.modules.users.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer access token."""
    if credentials is None:
        raise UnauthorizedException("Not authenticated")

    payload = verify_token(credentials.credentials)
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type")

    subject = payload.get("sub")
    if subject is None:
        raise UnauthorizedException("Invalid token")

    user = await session.get(User, int(subject))
    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")
    return user


def require_role(*roles: str):
    """Build a dependency that allows only users holding one of ``roles``."""

    async def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenException("Insufficient permissions")
        return user

    return guard

"""JWT utilities for authentication.

Uses PyJWT (actively maintained) rather than the unmaintained python-jose.
Verification failures are surfaced as domain ``UnauthorizedException`` so the
auth layer can translate them into HTTP 401 responses uniformly.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from jwt import PyJWTError

from src.config import settings
from src.core.exceptions import UnauthorizedException

logger = logging.getLogger(__name__)


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_expiration_minutes))
    to_encode.update({"exp": expire, "iat": now, "type": "access", "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a signed JWT refresh token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_expiration_days)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh", "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT, returning its claims.

    Raises UnauthorizedException if the token is invalid, tampered, or expired.
    """
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except PyJWTError as exc:
        logger.warning("Token verification failed: %s", exc)
        raise UnauthorizedException("Invalid or expired token") from exc

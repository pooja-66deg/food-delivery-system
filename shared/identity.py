"""Who is calling, decided without asking anyone.

The monolith answers this by loading the user row: ``get_current_user`` verifies
the token and then fetches the ``User`` it names, because the code around it
wants the whole object. A service cannot do that — the users table lives in
another database — and it must not do the obvious alternative either. If every
service called the users service on every request, the users service would be a
synchronous dependency of the entire platform, and its downtime would be
everyone's downtime. That is precisely the failure mode the split exists to
remove.

So identity here is derived from the token alone. The access token already
carries everything a service needs to authorise a request::

    sub  the user id         role  their role
    gen  session generation   jti  this token's id

Signature and expiry are checked locally against the shared secret. No network
call, no shared database, nothing that can be down.

The cost is honest and worth stating: a token stays valid until it expires, so a
deactivation or a password-change revocation reaches a service only after the
access token's lifetime. Keeping that lifetime short is the mitigation; a
synchronous call to the users service is not, because it would trade a bounded
staleness window for an unbounded availability coupling.

This module imports nothing from ``src`` on purpose — it is copied into each
service image as ``shared/``, and anything it reached for would have to be
copied with it.
"""

from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    """The caller, as far as a service needs to know.

    Deliberately not a ``User``: a service that only ever needs an id and a role
    should not be able to reach for an email address it has no copy of and would
    have to call another service to get.
    """

    user_id: int
    role: str
    #: This token's id, for a revocation blocklist.
    token_id: Optional[str] = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def identity_from_claims(claims: dict[str, Any]) -> Identity:
    """Build an Identity from already-verified token claims.

    Separate from the dependency so anything authenticating outside an HTTP
    request — a consumer replaying a context, a test — applies the same rules.
    """
    if claims.get("type") != "access":
        raise _unauthorized("Invalid token type")

    subject = claims.get("sub")
    role = claims.get("role")
    if subject is None or role is None:
        raise _unauthorized("Invalid token")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _unauthorized("Invalid token")

    return Identity(user_id=user_id, role=str(role), token_id=claims.get("jti"))


class JWTAuth:
    """Builds a service's auth dependencies from its own signing secret.

    Constructed once at import time by each service, so the secret is read from
    that service's settings rather than from a config object shared with the
    platform.
    """

    def __init__(self, secret: str, algorithm: str = "HS256"):
        self._secret = secret
        self._algorithm = algorithm

    def verify(self, token: str) -> Identity:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except PyJWTError as exc:
            raise _unauthorized("Invalid or expired token") from exc
        return identity_from_claims(claims)

    def identity(self):
        """Dependency resolving the caller, or 401."""

        async def dependency(
            credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
        ) -> Identity:
            if credentials is None:
                raise _unauthorized("Not authenticated")
            return self.verify(credentials.credentials)

        return dependency

    def require_role(self, *roles: str):
        """Dependency allowing only callers holding one of ``roles``.

        Mirrors the monolith's dependency of the same name, so a router can move
        between the two without its guards changing meaning.
        """
        resolve = self.identity()

        async def guard(identity: Identity = Depends(resolve)) -> Identity:
            if identity.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
                )
            return identity

        return guard

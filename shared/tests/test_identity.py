"""Identity resolved from the token alone — no users table, no users service.

The point of every test here is what is *absent*: no session, no redis, no HTTP
call. If any of these needed one, a service using this module would inherit the
availability of whatever it called.
"""
import jwt
import pytest
from fastapi import HTTPException

from src.shared.identity import Identity, JWTAuth, identity_from_claims

SECRET = "test-secret"
auth = JWTAuth(SECRET)


def _token(secret: str = SECRET, **claims) -> str:
    payload = {"sub": "7", "role": "customer", "gen": 0, "jti": "abc", "type": "access"}
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


class _Creds:
    """Stand-in for FastAPI's HTTPAuthorizationCredentials."""

    def __init__(self, token: str):
        self.credentials = token


def test_resolves_from_claims_alone():
    identity = auth.verify(_token())
    assert identity == Identity(user_id=7, role="customer", token_id="abc")


async def test_dependency_resolves_a_bearer_token():
    resolve = auth.identity()
    assert (await resolve(_Creds(_token()))).user_id == 7


async def test_missing_credentials_is_401():
    resolve = auth.identity()
    with pytest.raises(HTTPException) as exc:
        await resolve(None)
    assert exc.value.status_code == 401


def test_token_signed_with_another_secret_is_rejected():
    """The check that makes local verification safe at all."""
    with pytest.raises(HTTPException) as exc:
        auth.verify(_token(secret="not-our-secret"))
    assert exc.value.status_code == 401


def test_refresh_token_is_not_an_access_token():
    """A refresh token authenticates a token exchange, not a request."""
    with pytest.raises(HTTPException, match="Invalid token type"):
        auth.verify(_token(type="refresh"))


def test_tampered_token_is_rejected():
    token = _token()
    with pytest.raises(HTTPException):
        auth.verify(token[:-4] + "aaaa")


@pytest.mark.parametrize("claims", [
    {"role": "customer"},                  # no sub
    {"sub": "7"},                          # no role
    {"sub": "not-a-number", "role": "x"},  # unusable sub
])
def test_incomplete_claims_are_rejected(claims):
    with pytest.raises(HTTPException):
        identity_from_claims({"type": "access", **claims})


async def test_require_role_allows_a_listed_role():
    guard = auth.require_role("driver", "admin")
    identity = Identity(user_id=1, role="admin")
    assert await guard(identity) is identity


async def test_require_role_rejects_an_unlisted_one():
    guard = auth.require_role("driver", "admin")
    with pytest.raises(HTTPException) as exc:
        await guard(Identity(user_id=1, role="customer"))
    assert exc.value.status_code == 403

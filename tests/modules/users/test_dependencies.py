"""Tests for auth dependencies (current user + role guard)."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.jwt import create_access_token
from src.modules.users import dependencies, service
from src.modules.users.schemas import UserRegister


def _registration(**overrides) -> UserRegister:
    base = dict(
        email="dep@example.com",
        phone="+15552220000",
        first_name="Dep",
        last_name="User",
        password="supersecret1",
    )
    base.update(overrides)
    return UserRegister(**base)


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_get_current_user_returns_user_for_valid_token(db_session):
    user = await service.register_user(db_session, _registration())
    token = create_access_token({"sub": str(user.id), "role": user.role})

    result = await dependencies.get_current_user(_creds(token), db_session)

    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_credentials(db_session):
    with pytest.raises(UnauthorizedException):
        await dependencies.get_current_user(None, db_session)


@pytest.mark.asyncio
async def test_get_current_user_rejects_unknown_user(db_session):
    token = create_access_token({"sub": "99999", "role": "customer"})

    with pytest.raises(UnauthorizedException):
        await dependencies.get_current_user(_creds(token), db_session)


@pytest.mark.asyncio
async def test_require_role_allows_matching_role(db_session):
    user = await service.register_user(db_session, _registration())  # role=customer

    guard = dependencies.require_role("customer")
    assert await guard(user) is user


@pytest.mark.asyncio
async def test_require_role_forbids_other_role(db_session):
    user = await service.register_user(db_session, _registration())  # role=customer

    guard = dependencies.require_role("admin")
    with pytest.raises(ForbiddenException):
        await guard(user)

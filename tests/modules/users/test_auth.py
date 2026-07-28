"""Tests for authentication flows (password login, OTP)."""

import pytest

from src.core.exceptions import UnauthorizedException
from src.core.jwt import verify_token
from src.modules.users import service
from src.modules.users.schemas import UserRegister


def _registration(**overrides) -> UserRegister:
    base = dict(
        email="login@example.com",
        phone="+15551234000",
        first_name="Log",
        last_name="In",
        password="supersecret1",
    )
    base.update(overrides)
    return UserRegister(**base)


@pytest.mark.asyncio
async def test_login_returns_tokens_with_identity(db_session):
    user = await service.register_user(db_session, _registration())

    tokens = await service.login(db_session, "login@example.com", "supersecret1")

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"
    payload = verify_token(tokens.access_token)
    assert payload["sub"] == str(user.id)
    assert payload["role"] == "customer"


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(db_session):
    await service.register_user(db_session, _registration())

    with pytest.raises(UnauthorizedException):
        await service.login(db_session, "login@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_login_unknown_email_rejected(db_session):
    with pytest.raises(UnauthorizedException):
        await service.login(db_session, "nobody@example.com", "supersecret1")

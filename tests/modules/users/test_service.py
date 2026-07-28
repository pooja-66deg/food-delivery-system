"""Tests for the users domain service layer."""

import pytest
from pydantic import ValidationError

from src.core.exceptions import ConflictException
from src.modules.users import service
from src.modules.users.schemas import UserRegister


def _registration(**overrides) -> UserRegister:
    base = dict(
        email="user@example.com",
        phone="+15551230000",
        first_name="Test",
        last_name="User",
        password="supersecret1",
    )
    base.update(overrides)
    return UserRegister(**base)


@pytest.mark.asyncio
async def test_register_user_hashes_password(db_session):
    data = UserRegister(
        email="alice@example.com",
        phone="+15551230001",
        first_name="Alice",
        last_name="Smith",
        password="supersecret1",
    )

    user = await service.register_user(db_session, data)

    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.role == "customer"
    # Password must be stored hashed, never in plaintext.
    assert user.hashed_password != "supersecret1"
    assert service.verify_password("supersecret1", user.hashed_password)


@pytest.mark.asyncio
async def test_register_defaults_to_customer_role(db_session):
    user = await service.register_user(db_session, _registration())
    assert user.role == "customer"


@pytest.mark.asyncio
async def test_register_with_restaurant_role(db_session):
    user = await service.register_user(
        db_session, _registration(email="owner@example.com", phone="+15550000009", role="restaurant")
    )
    assert user.role == "restaurant"


def test_register_rejects_privileged_role():
    with pytest.raises(ValidationError):
        _registration(role="admin")


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(db_session):
    await service.register_user(db_session, _registration(email="dup@example.com", phone="+15551230001"))

    with pytest.raises(ConflictException):
        await service.register_user(
            db_session, _registration(email="dup@example.com", phone="+15551230002")
        )


@pytest.mark.asyncio
async def test_register_duplicate_phone_rejected(db_session):
    await service.register_user(db_session, _registration(email="a@example.com", phone="+15559990000"))

    with pytest.raises(ConflictException):
        await service.register_user(
            db_session, _registration(email="b@example.com", phone="+15559990000")
        )

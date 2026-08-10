import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.service import bootstrap_admin, reset_admin_password
from shared.errors import NotFoundException, UnauthorizedException


@pytest.mark.asyncio
async def test_bootstrap_admin_sets_password_reset_required(db_session: AsyncSession):
    """Bootstrap creates admin with password_reset_required=True."""
    user = await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    assert user.email == "admin@test.com"
    assert user.role == "admin"
    assert user.password_reset_required is True
    assert user.is_active is True


@pytest.mark.asyncio
async def test_bootstrap_admin_only_once(db_session: AsyncSession):
    """Calling bootstrap twice raises error."""
    await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    with pytest.raises(Exception, match="Admin account already exists"):
        await bootstrap_admin(db_session, "admin2@test.com", "TempPassword123")


@pytest.mark.asyncio
async def test_reset_admin_password_success(db_session: AsyncSession):
    """Resetting password clears password_reset_required flag."""
    user = await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    user = await reset_admin_password(
        db_session,
        "admin@test.com",
        "TempPassword123",
        "NewPassword456"
    )
    assert user.password_reset_required is False
    assert user.email == "admin@test.com"


@pytest.mark.asyncio
async def test_reset_admin_password_wrong_old_password(db_session: AsyncSession):
    """Resetting with wrong old password raises UnauthorizedException."""
    await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    with pytest.raises(UnauthorizedException):
        await reset_admin_password(
            db_session,
            "admin@test.com",
            "WrongPassword",
            "NewPassword456"
        )


@pytest.mark.asyncio
async def test_reset_admin_password_nonexistent_user(db_session: AsyncSession):
    """Resetting password for nonexistent user raises NotFoundException."""
    with pytest.raises(NotFoundException):
        await reset_admin_password(
            db_session,
            "nonexistent@test.com",
            "OldPassword",
            "NewPassword456"
        )

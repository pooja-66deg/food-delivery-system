"""Bootstrapping the first admin, and the forced reset its first login demands.

``reset_admin_password`` is reachable without a token — the flow that leads to it
has not issued one yet. What keeps that safe is the set of conditions it accepts,
so those are what these tests pin: an admin, still flagged for reset, with the
right current password. Anything else gets one indistinguishable refusal, because
an unauthenticated endpoint that says "no such account" is an oracle.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.service import bootstrap_admin, register_user, reset_admin_password
from app.schemas import UserRegister
from shared.errors import UnauthorizedException


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
async def test_reset_admin_password_evicts_existing_sessions(db_session: AsyncSession):
    """The generation bump is what makes the reset actually take the account back.

    Without it a token minted before the change keeps working for the rest of its
    lifetime, and a refresh token captured beforehand keeps rotating into new ones
    indefinitely — so whoever had the account never loses it.
    """
    admin = await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    before = admin.session_generation

    updated = await reset_admin_password(
        db_session, "admin@test.com", "TempPassword123", "NewPassword456"
    )

    assert updated.session_generation == before + 1


@pytest.mark.asyncio
async def test_reset_admin_password_refuses_a_non_admin(db_session: AsyncSession):
    """A customer's password is not resettable here, even with the right password.

    Without the role check this route was a password-change primitive for any
    account on the platform, callable with no Authorization header at all.
    """
    await register_user(db_session, UserRegister(
        email="cara@example.com", phone="+919876543210",
        first_name="Cara", last_name="Customer",
        password="supersecret1", role="customer",
    ))

    with pytest.raises(UnauthorizedException):
        await reset_admin_password(
            db_session, "cara@example.com", "supersecret1", "NewPassword456"
        )


@pytest.mark.asyncio
async def test_reset_admin_password_refuses_once_already_reset(db_session: AsyncSession):
    """The route exists for one state; an admin past it uses change-password."""
    await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")
    await reset_admin_password(
        db_session, "admin@test.com", "TempPassword123", "NewPassword456"
    )

    with pytest.raises(UnauthorizedException):
        await reset_admin_password(
            db_session, "admin@test.com", "NewPassword456", "ThirdPassword789"
        )


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
async def test_reset_admin_password_does_not_reveal_whether_an_account_exists(
    db_session: AsyncSession,
):
    """An unknown address is refused exactly as a wrong password is.

    It used to raise NotFoundException, which the error layer renders as a 404
    echoing the submitted address back — two unauthenticated requests were then
    enough to learn whether any given email had an account here. This is the
    oracle request_password_reset goes out of its way not to be.
    """
    await bootstrap_admin(db_session, "admin@test.com", "TempPassword123")

    with pytest.raises(UnauthorizedException) as unknown:
        await reset_admin_password(
            db_session, "nonexistent@test.com", "OldPassword", "NewPassword456"
        )
    with pytest.raises(UnauthorizedException) as wrong_password:
        await reset_admin_password(
            db_session, "admin@test.com", "WrongPassword", "NewPassword456"
        )

    assert str(unknown.value) == str(wrong_password.value)
    assert unknown.value.status_code == wrong_password.value.status_code

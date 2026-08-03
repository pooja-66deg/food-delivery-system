"""Profile and address management for the users domain."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, NotFoundException
from src.modules.users.models import Address, User
from src.modules.users.schemas import AddressCreate, AddressUpdate, UserUpdate


async def update_profile(session: AsyncSession, user: User, data: UserUpdate) -> User:
    """Apply profile edits. Phone changes are checked for uniqueness."""
    updates = data.model_dump(exclude_unset=True)

    new_phone = updates.get("phone")
    if new_phone is not None and new_phone != user.phone:
        clash = await session.scalar(select(User).where(User.phone == new_phone))
        if clash is not None:
            raise ConflictException("Phone already registered")

    for field, value in updates.items():
        setattr(user, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictException("Phone already registered")
    await session.refresh(user)
    return user


async def add_address(session: AsyncSession, user: User, data: AddressCreate) -> Address:
    """Create an address for the user. Setting it default unsets any other."""
    if data.is_default:
        await _clear_default(session, user)

    address = Address(user_id=user.id, **data.model_dump())
    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address


async def list_addresses(session: AsyncSession, user: User) -> list[Address]:
    """Return all addresses belonging to the user, newest first."""
    result = await session.scalars(
        select(Address).where(Address.user_id == user.id).order_by(Address.id.desc())
    )
    return list(result)


async def update_address(
    session: AsyncSession, user: User, address_id: int, data: AddressUpdate
) -> Address:
    """Apply partial edits to an address the user owns; 404 if it is not theirs.

    Promoting an address to default unsets any other, matching ``add_address``.
    """
    address = await _owned_address(session, user, address_id)
    updates = data.model_dump(exclude_unset=True)
    # line2 is the only nullable column, so a null anywhere else means "leave
    # this field alone" rather than "clear it".
    updates = {k: v for k, v in updates.items() if v is not None or k == "line2"}

    if updates.get("is_default"):
        await _clear_default(session, user)

    for field, value in updates.items():
        setattr(address, field, value)

    await session.commit()
    await session.refresh(address)
    return address


async def delete_address(session: AsyncSession, user: User, address_id: int) -> None:
    """Delete an address the user owns; 404 if it is not theirs."""
    address = await _owned_address(session, user, address_id)
    await session.delete(address)
    await session.commit()


async def _owned_address(session: AsyncSession, user: User, address_id: int) -> Address:
    address = await session.get(Address, address_id)
    if address is None or address.user_id != user.id:
        raise NotFoundException("Address", str(address_id))
    return address


async def _clear_default(session: AsyncSession, user: User) -> None:
    result = await session.scalars(
        select(Address).where(Address.user_id == user.id, Address.is_default.is_(True))
    )
    for address in result:
        address.is_default = False

"""Profile and address management for the users domain."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictException, NotFoundException
from app.providers import GeocodeProvider, geocode_provider
from app import outbox
from app.models import Address, User
from app.schemas import AddressCreate, AddressUpdate, UserUpdate

# Editing any of these invalidates a stored geocode; editing anything else
# (label, is_default, line2) does not, so it costs no API call.
_LOCATION_FIELDS = ("line1", "city", "postal_code")


async def update_profile(session: AsyncSession, user: User, data: UserUpdate) -> User:
    """Apply profile edits. Phone changes are checked for uniqueness.

    Nulls are dropped, the same reading ``update_address`` applies: nothing on a
    user is nullable, so an explicit null means "leave this alone" rather than
    "clear it". ``exclude_unset`` kept it, and the write then failed the NOT NULL
    constraint — which the handler below reported as ``Phone already registered``
    whatever the column had actually been. ``{"first_name": null}`` answered 409
    telling the caller to pick a different phone number.
    """
    updates = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
    }

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
        # Narrow, because this handler used to claim a phone conflict for every
        # constraint in the table. Phone is the only unique column here, so
        # anything else reaching this point is not a conflict and should not be
        # described as one.
        raise ConflictException("Phone already registered")
    await session.refresh(user)
    return user


async def add_address(
    session: AsyncSession,
    user: User,
    data: AddressCreate,
    geocoder: GeocodeProvider | None = None,
) -> Address:
    """Create an address for the user. Setting it default unsets any other.

    The address is geocoded on the way in when a provider is configured.
    Geocoding never fails the write: an unresolvable address saves with null
    coordinates and simply is not mappable.
    """
    if data.is_default:
        await _clear_default(session, user)

    address = Address(user_id=user.id, **data.model_dump())
    point = await (geocoder or geocode_provider()).geocode(
        data.line1, data.city, data.postal_code
    )
    if point is not None:
        address.latitude = point.latitude
        address.longitude = point.longitude

    session.add(address)
    await session.flush()  # assigns address.id, which the event needs
    publish_address(session, address)
    await session.commit()
    await session.refresh(address)
    return address


def publish_address(session: AsyncSession, address: Address) -> None:
    """Announce an address to the services that deliver to it.

    The orders service keeps a copy: checkout has to know where an order is
    going, and asking this service for it on every checkout would make placing
    an order fail whenever this one is slow.

    City and coordinates only — never the street line. A consumer that needs to
    measure a distance and match a city does not need to know where somebody
    lives, and what it cannot receive it cannot leak.
    """
    outbox.record_event(
        session, "address-events", str(address.id),
        {
            "address_id": address.id,
            "user_id": address.user_id,
            "city": address.city,
            "latitude": address.latitude,
            "longitude": address.longitude,
        },
    )


async def list_addresses(session: AsyncSession, user: User) -> list[Address]:
    """Return all addresses belonging to the user, newest first."""
    result = await session.scalars(
        select(Address).where(Address.user_id == user.id).order_by(Address.id.desc())
    )
    return list(result)


async def update_address(
    session: AsyncSession,
    user: User,
    address_id: int,
    data: AddressUpdate,
    geocoder: GeocodeProvider | None = None,
) -> Address:
    """Apply partial edits to an address the user owns; 404 if it is not theirs.

    Promoting an address to default unsets any other, matching ``add_address``.
    Re-geocodes only when the location actually moved.
    """
    address = await _owned_address(session, user, address_id)
    updates = data.model_dump(exclude_unset=True)
    # line2 is the only nullable column, so a null anywhere else means "leave
    # this field alone" rather than "clear it".
    updates = {k: v for k, v in updates.items() if v is not None or k == "line2"}

    if updates.get("is_default"):
        await _clear_default(session, user)

    moved = any(
        field in updates and updates[field] != getattr(address, field)
        for field in _LOCATION_FIELDS
    )

    for field, value in updates.items():
        setattr(address, field, value)

    if moved:
        point = await (geocoder or geocode_provider()).geocode(
            address.line1, address.city, address.postal_code
        )
        # A failed re-geocode clears the old point rather than keeping it: stale
        # coordinates for a new street address would route to the wrong place,
        # and ungeocoded fails visibly where wrong coordinates fail silently.
        address.latitude = point.latitude if point else None
        address.longitude = point.longitude if point else None

    # Republished on every edit, not just a move: a city change alters which
    # restaurants can deliver here, and a consumer holding the old one would
    # accept an order nobody can fulfil.
    publish_address(session, address)
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

"""Per-user outbound channel preferences and push device registrations."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.models import Channel, DeviceToken, NotificationPreference
from src.modules.notifications.schemas import PreferenceUpdate

MAX_DEVICES_PER_USER = 10


async def get_preferences(session: AsyncSession, user_id: int) -> NotificationPreference:
    """The user's preferences, creating the default row on first read.

    Returned unsaved when it does not exist yet, so a plain GET does not write.
    The column defaults and this object therefore have to agree — they are both
    "email and push on, SMS off".
    """
    existing = await session.get(NotificationPreference, user_id)
    if existing is not None:
        return existing
    return NotificationPreference(
        user_id=user_id, email_enabled=True, sms_enabled=False, push_enabled=True
    )


async def update_preferences(
    session: AsyncSession, user_id: int, data: PreferenceUpdate
) -> NotificationPreference:
    """Apply the fields the caller sent, leaving the rest alone."""
    prefs = await session.get(NotificationPreference, user_id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        session.add(prefs)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    await session.commit()
    await session.refresh(prefs)
    return prefs


def allows(prefs: NotificationPreference, channel: Channel) -> bool:
    """Whether the user accepts this channel."""
    return {
        Channel.EMAIL: prefs.email_enabled,
        Channel.SMS: prefs.sms_enabled,
        Channel.PUSH: prefs.push_enabled,
    }.get(channel, False)


async def register_device(
    session: AsyncSession, user_id: int, token: str, platform: str = "web"
) -> DeviceToken:
    """Register (or re-point) a push token for a user.

    Re-registering an existing token moves it to the caller rather than failing:
    the same device legitimately changes hands, and the alternative is a user
    who can never receive push because someone else registered their token
    first.
    """
    existing = await session.scalar(select(DeviceToken).where(DeviceToken.token == token))
    if existing is not None:
        existing.user_id = user_id
        existing.platform = platform
        await session.commit()
        await session.refresh(existing)
        return existing

    # Keep the newest devices and drop the oldest beyond the cap, so a user who
    # reinstalls repeatedly does not accumulate dead tokens forever.
    await _evict_oldest_beyond_cap(session, user_id)
    device = DeviceToken(user_id=user_id, token=token, platform=platform)
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


async def _evict_oldest_beyond_cap(session: AsyncSession, user_id: int) -> None:
    stmt = (
        select(DeviceToken.id)
        .where(DeviceToken.user_id == user_id)
        .order_by(DeviceToken.id.desc())
        .offset(MAX_DEVICES_PER_USER - 1)
    )
    stale = list(await session.scalars(stmt))
    if stale:
        await session.execute(delete(DeviceToken).where(DeviceToken.id.in_(stale)))


async def unregister_device(session: AsyncSession, user_id: int, token: str) -> bool:
    """Remove one of the user's tokens. Returns whether anything was removed.

    Scoped to the caller so one user cannot unregister another's device.
    """
    result = await session.execute(
        delete(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.token == token)
    )
    await session.commit()
    return bool(result.rowcount)


async def list_devices(session: AsyncSession, user_id: int) -> list[DeviceToken]:
    stmt = select(DeviceToken).where(DeviceToken.user_id == user_id).order_by(DeviceToken.id.desc())
    return list(await session.scalars(stmt))


async def device_tokens(session: AsyncSession, user_id: int) -> list[str]:
    """Just the token strings, for dispatch."""
    return [d.token for d in await list_devices(session, user_id)]

"""Channel preferences and push device registration."""
import pytest

from src.modules.notifications import preferences
from src.modules.notifications.models import Channel, DeviceToken
from src.modules.notifications.schemas import PreferenceUpdate
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister


async def _user(db_session, email="pref@example.com", phone="+15559810001"):
    return await users_service.register_user(
        db_session,
        UserRegister(email=email, phone=phone, first_name="P", last_name="R",
                     password="supersecret1", role="customer"),
    )


@pytest.mark.asyncio
async def test_defaults_are_email_and_push_on_sms_off(db_session):
    """SMS costs money per message, so it is the one channel you opt into."""
    user = await _user(db_session)

    prefs = await preferences.get_preferences(db_session, user.id)

    assert prefs.email_enabled is True
    assert prefs.push_enabled is True
    assert prefs.sms_enabled is False


@pytest.mark.asyncio
async def test_reading_preferences_does_not_write_a_row(db_session):
    """A plain GET must not persist anything, so absence stays a valid state."""
    user = await _user(db_session)

    await preferences.get_preferences(db_session, user.id)

    from src.modules.notifications.models import NotificationPreference
    assert await db_session.get(NotificationPreference, user.id) is None


@pytest.mark.asyncio
async def test_update_creates_the_row_and_applies_only_sent_fields(db_session):
    user = await _user(db_session)

    updated = await preferences.update_preferences(
        db_session, user.id, PreferenceUpdate(sms_enabled=True)
    )

    assert updated.sms_enabled is True
    # Untouched channels keep their defaults rather than being reset.
    assert updated.email_enabled is True
    assert updated.push_enabled is True


@pytest.mark.asyncio
async def test_update_is_repeatable_on_an_existing_row(db_session):
    user = await _user(db_session)
    await preferences.update_preferences(db_session, user.id, PreferenceUpdate(sms_enabled=True))

    updated = await preferences.update_preferences(
        db_session, user.id, PreferenceUpdate(email_enabled=False)
    )

    assert updated.email_enabled is False
    assert updated.sms_enabled is True


@pytest.mark.asyncio
async def test_allows_maps_each_channel_to_its_flag(db_session):
    user = await _user(db_session)
    prefs = await preferences.update_preferences(
        db_session, user.id,
        PreferenceUpdate(email_enabled=False, sms_enabled=True, push_enabled=False),
    )

    assert preferences.allows(prefs, Channel.SMS) is True
    assert preferences.allows(prefs, Channel.EMAIL) is False
    assert preferences.allows(prefs, Channel.PUSH) is False
    # LOG is the in-app feed and is never gated by a preference.
    assert preferences.allows(prefs, Channel.LOG) is False


@pytest.mark.asyncio
async def test_register_device_stores_a_token(db_session):
    user = await _user(db_session)

    device = await preferences.register_device(db_session, user.id, "tok-abcdefgh", "android")

    assert device.token == "tok-abcdefgh"
    assert device.platform == "android"
    assert await preferences.device_tokens(db_session, user.id) == ["tok-abcdefgh"]


@pytest.mark.asyncio
async def test_reregistering_a_token_repoints_it_instead_of_failing(db_session):
    """A shared phone or a reinstall must not lock the new owner out of push."""
    first = await _user(db_session)
    second = await _user(db_session, "other@example.com", "+15559810002")
    await preferences.register_device(db_session, first.id, "tok-abcdefgh")

    moved = await preferences.register_device(db_session, second.id, "tok-abcdefgh")

    assert moved.user_id == second.id
    assert await preferences.device_tokens(db_session, first.id) == []
    assert await preferences.device_tokens(db_session, second.id) == ["tok-abcdefgh"]


@pytest.mark.asyncio
async def test_device_list_is_capped_keeping_the_newest(db_session):
    user = await _user(db_session)
    for i in range(preferences.MAX_DEVICES_PER_USER + 3):
        await preferences.register_device(db_session, user.id, f"tok-{i:08d}")

    tokens = await preferences.device_tokens(db_session, user.id)

    assert len(tokens) == preferences.MAX_DEVICES_PER_USER
    assert "tok-00000012" in tokens   # newest kept
    assert "tok-00000000" not in tokens  # oldest evicted


@pytest.mark.asyncio
async def test_unregister_removes_the_token(db_session):
    user = await _user(db_session)
    await preferences.register_device(db_session, user.id, "tok-abcdefgh")

    assert await preferences.unregister_device(db_session, user.id, "tok-abcdefgh") is True
    assert await preferences.device_tokens(db_session, user.id) == []


@pytest.mark.asyncio
async def test_unregister_cannot_touch_another_users_device(db_session):
    owner = await _user(db_session)
    other = await _user(db_session, "other@example.com", "+15559810002")
    await preferences.register_device(db_session, owner.id, "tok-abcdefgh")

    assert await preferences.unregister_device(db_session, other.id, "tok-abcdefgh") is False
    # Still there, still the original owner's.
    remaining = await db_session.get(DeviceToken, 1)
    assert remaining is not None and remaining.user_id == owner.id

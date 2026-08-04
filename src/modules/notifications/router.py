"""HTTP routes for notifications, channel preferences, and push devices."""
from fastapi import APIRouter, Depends, status

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database import get_db
from src.core.exceptions import NotFoundException
from src.modules.notifications import preferences, service
from src.modules.notifications.schemas import (
    DeviceRead,
    DeviceRegister,
    NotificationDeliveryRead,
    NotificationRead,
    PreferenceRead,
    PreferenceUpdate,
)
from src.modules.users.dependencies import get_current_user
from src.modules.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_my_notifications(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    return await service.list_for_user(session, user.id)


@router.get("/deliveries", response_model=list[NotificationDeliveryRead])
async def list_my_deliveries(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    """What we tried to send this user over email/SMS/push, and whether it landed."""
    return await service.list_deliveries(session, user.id)


@router.get("/preferences", response_model=PreferenceRead)
async def get_my_preferences(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    return await preferences.get_preferences(session, user.id)


@router.patch("/preferences", response_model=PreferenceRead)
async def update_my_preferences(
    data: PreferenceUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await preferences.update_preferences(session, user.id, data)


@router.get("/devices", response_model=list[DeviceRead])
async def list_my_devices(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    return await preferences.list_devices(session, user.id)


@router.post("/devices", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_my_device(
    data: DeviceRegister,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Register a push token. Re-posting a known token re-points it to the caller."""
    return await preferences.register_device(session, user.id, data.token, data.platform)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_my_device(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if not await preferences.unregister_device(session, user.id, token):
        # 404 rather than 204: scoped to the caller, so "not yours" and "not
        # there" are the same answer and neither confirms the token exists.
        raise NotFoundException("Device", token)

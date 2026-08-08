"""HTTP surface. Same paths and shapes as the monolith's notifications router,
so the frontend does not know it moved.

The one difference is the guard: ``Identity`` instead of ``User``. Everything
here is scoped to the caller's own id, which is the only fact about them this
service needs — and the only one it can get without asking another service.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import preferences, service
from app.auth import auth
from app.db import get_db
from app.schemas import (
    DeviceRead,
    DeviceRegister,
    NotificationDeliveryRead,
    NotificationRead,
    PreferenceRead,
    PreferenceUpdate,
)
from shared.identity import Identity

router = APIRouter(prefix="/notifications", tags=["notifications"])

_caller = auth.identity()


@router.get("", response_model=list[NotificationRead])
async def list_my_notifications(
    identity: Identity = Depends(_caller), session: AsyncSession = Depends(get_db)
):
    return await service.list_for_user(session, identity.user_id)


@router.get("/deliveries", response_model=list[NotificationDeliveryRead])
async def list_my_deliveries(
    identity: Identity = Depends(_caller), session: AsyncSession = Depends(get_db)
):
    return await service.list_deliveries(session, identity.user_id)


@router.get("/preferences", response_model=PreferenceRead)
async def get_my_preferences(
    identity: Identity = Depends(_caller), session: AsyncSession = Depends(get_db)
):
    return await preferences.get_preferences(session, identity.user_id)


@router.patch("/preferences", response_model=PreferenceRead)
async def update_my_preferences(
    data: PreferenceUpdate,
    identity: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    return await preferences.update_preferences(session, identity.user_id, data)


@router.get("/devices", response_model=list[DeviceRead])
async def list_my_devices(
    identity: Identity = Depends(_caller), session: AsyncSession = Depends(get_db)
):
    return await preferences.list_devices(session, identity.user_id)


@router.post("/devices", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def register_my_device(
    data: DeviceRegister,
    identity: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    return await preferences.register_device(session, identity.user_id, data.token, data.platform)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_my_device(
    token: str,
    identity: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
):
    # Scoped to the caller, so one user cannot unregister another's device.
    # Deleting something already gone is still success — the caller's intent is
    # satisfied either way.
    await preferences.unregister_device(session, identity.user_id, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

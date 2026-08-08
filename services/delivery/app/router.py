"""HTTP surface. Same paths and shapes as the monolith's delivery router, so the
frontend does not know it moved.

The guards take ``Identity`` instead of ``User``: an id and a role, which is all
these routes ever needed, and all this service can know without asking another.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import location, service
from app.auth import auth
from app.db import get_db
from app.redis_client import get_redis
from app.schemas import AvailableDriver, DeliveryRead, TrackingRead
from shared.identity import Identity

router = APIRouter(prefix="/delivery", tags=["delivery"])

_driver = auth.require_role("driver", "admin")
_restaurant = auth.require_role("restaurant", "admin")
_admin = auth.require_role("admin")
_caller = auth.identity()


class StatusBody(BaseModel):
    online: bool


class LocationBody(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class ReassignBody(BaseModel):
    driver_id: int


@router.get("/assignments", response_model=list[DeliveryRead])
async def my_assignments(
    driver: Identity = Depends(_driver), session: AsyncSession = Depends(get_db)
):
    return await service.list_for_driver(session, driver.user_id)


@router.post("/status")
async def set_status(
    body: StatusBody, driver: Identity = Depends(_driver), redis=Depends(get_redis)
):
    if redis is not None:
        await location.set_online(redis, driver.user_id, body.online)
    return {"driver_id": driver.user_id, "online": body.online}


@router.post("/location")
async def update_location(
    body: LocationBody, driver: Identity = Depends(_driver), redis=Depends(get_redis)
):
    if redis is not None:
        await location.update_location(redis, driver.user_id, body.latitude, body.longitude)
    return {"driver_id": driver.user_id, "latitude": body.latitude, "longitude": body.longitude}


@router.get("/nearby")
async def nearby(
    latitude: float,
    longitude: float,
    radius_km: float = 10,
    admin: Identity = Depends(_admin),
    redis=Depends(get_redis),
):
    ids = await location.nearby_driver_ids(redis, latitude, longitude, radius_km) if redis else []
    return {"driver_ids": ids}


@router.post("/orders/{order_id}/accept", response_model=DeliveryRead)
async def accept(
    order_id: int,
    driver: Identity = Depends(_driver),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.accept_assignment(session, driver.user_id, order_id, redis=redis)


@router.post("/orders/{order_id}/reject", response_model=DeliveryRead)
async def reject(
    order_id: int,
    driver: Identity = Depends(_driver),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.reject_assignment(session, driver.user_id, order_id, redis=redis)


@router.post("/orders/{order_id}/pickup", response_model=DeliveryRead)
async def pickup(
    order_id: int,
    driver: Identity = Depends(_driver),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.pickup(session, driver.user_id, order_id, redis=redis)


@router.post("/orders/{order_id}/deliver", response_model=DeliveryRead)
async def deliver(
    order_id: int,
    driver: Identity = Depends(_driver),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.deliver(session, driver.user_id, order_id, redis=redis)


@router.get("/orders/{order_id}/tracking", response_model=TrackingRead)
async def tracking(
    order_id: int,
    caller: Identity = Depends(_caller),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.tracking_for_order(
        session, caller.user_id, caller.role, redis, order_id
    )


@router.get("/available-drivers", response_model=list[AvailableDriver])
async def available_drivers(
    restaurant: Identity = Depends(_restaurant), session: AsyncSession = Depends(get_db)
):
    """Drivers not currently on an active delivery."""
    return await service.list_available_drivers(session)


@router.post("/orders/{order_id}/reassign", response_model=DeliveryRead)
async def reassign(
    order_id: int,
    body: ReassignBody,
    restaurant: Identity = Depends(_restaurant),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Reassign a delivery to a different driver (restaurant override)."""
    return await service.reassign_delivery_for_order(
        session, restaurant, order_id, body.driver_id, redis=redis
    )

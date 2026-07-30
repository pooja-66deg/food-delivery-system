"""HTTP routes for the delivery domain (driver-facing + tracking)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.infrastructure.redis import get_redis
from src.modules.delivery import location, service
from src.modules.delivery.schemas import DeliveryRead
from src.modules.users.dependencies import get_current_user, require_role
from src.modules.users.models import User

router = APIRouter(prefix="/delivery", tags=["delivery"])

_driver = require_role("driver", "admin")


class StatusBody(BaseModel):
    online: bool


class LocationBody(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


@router.get("/assignments", response_model=list[DeliveryRead])
async def my_assignments(driver: User = Depends(_driver), session: AsyncSession = Depends(get_db)):
    return await service.list_for_driver(session, driver.id)


@router.post("/status")
async def set_status(body: StatusBody, driver: User = Depends(_driver), redis=Depends(get_redis)):
    await location.set_online(redis, driver.id, body.online)
    return {"driver_id": driver.id, "online": body.online}


@router.post("/location")
async def update_location(body: LocationBody, driver: User = Depends(_driver), redis=Depends(get_redis)):
    await location.update_location(redis, driver.id, body.latitude, body.longitude)
    return {"driver_id": driver.id, "latitude": body.latitude, "longitude": body.longitude}


@router.get("/nearby")
async def nearby(
    latitude: float, longitude: float, radius_km: float = 10,
    admin: User = Depends(require_role("admin")), redis=Depends(get_redis),
):
    ids = await location.nearby_driver_ids(redis, latitude, longitude, radius_km)
    return {"driver_ids": ids}


@router.post("/orders/{order_id}/accept", response_model=DeliveryRead)
async def accept(order_id: int, driver: User = Depends(_driver), session: AsyncSession = Depends(get_db)):
    return await service.accept_assignment(session, driver, order_id)


@router.post("/orders/{order_id}/reject", response_model=DeliveryRead)
async def reject(order_id: int, driver: User = Depends(_driver),
                 session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.reject_assignment(session, driver, order_id, redis=redis)


@router.post("/orders/{order_id}/pickup", response_model=DeliveryRead)
async def pickup(order_id: int, driver: User = Depends(_driver), session: AsyncSession = Depends(get_db)):
    return await service.pickup(session, driver, order_id)


@router.post("/orders/{order_id}/deliver", response_model=DeliveryRead)
async def deliver(order_id: int, driver: User = Depends(_driver), session: AsyncSession = Depends(get_db)):
    return await service.deliver(session, driver, order_id)


@router.get("/orders/{order_id}/tracking")
async def tracking(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    return await service.tracking_for_order(session, user, redis, order_id)

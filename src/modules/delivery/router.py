"""HTTP routes for the delivery domain (driver-facing)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.modules.delivery import service
from src.modules.delivery.schemas import DeliveryRead
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/delivery", tags=["delivery"])


@router.get("/assignments", response_model=list[DeliveryRead])
async def my_assignments(
    driver: User = Depends(require_role("driver", "admin")),
    session: AsyncSession = Depends(get_db),
):
    return await service.list_for_driver(session, driver.id)


@router.post("/orders/{order_id}/pickup", response_model=DeliveryRead)
async def pickup(
    order_id: int,
    driver: User = Depends(require_role("driver", "admin")),
    session: AsyncSession = Depends(get_db),
):
    return await service.pickup(session, driver, order_id)


@router.post("/orders/{order_id}/deliver", response_model=DeliveryRead)
async def deliver(
    order_id: int,
    driver: User = Depends(require_role("driver", "admin")),
    session: AsyncSession = Depends(get_db),
):
    return await service.deliver(session, driver, order_id)

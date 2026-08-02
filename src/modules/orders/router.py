"""HTTP routes for the orders domain."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database import get_db
from src.adapters.redis import get_redis
from src.modules.cart.schemas import CheckoutRequest
from src.modules.orders import service
from src.modules.orders.models import OrderStatus
from src.modules.orders.schemas import OrderRead, OrderSummary
from src.modules.users.dependencies import get_current_user, require_role
from src.modules.users.models import User

router = APIRouter(prefix="/orders", tags=["orders"])


class RejectBody(BaseModel):
    reason: str | None = None


class StatusBody(BaseModel):
    to: OrderStatus


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout(data: CheckoutRequest, user: User = Depends(require_role("customer")),
                   session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.create_order_from_checkout(redis, session, user, data)


@router.get("", response_model=list[OrderSummary])
async def list_my_orders(limit: int = 20, offset: int = 0,
                         user: User = Depends(require_role("customer")), session: AsyncSession = Depends(get_db)):
    return await service.list_orders(session, user.id, limit, offset)


@router.get("/restaurant/{restaurant_id}", response_model=list[OrderRead])
async def restaurant_orders(restaurant_id: int,
                            user: User = Depends(require_role("restaurant", "admin")),
                            session: AsyncSession = Depends(get_db)):
    return await service.list_orders_for_restaurant(session, user, restaurant_id)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: int, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_db)):
    return await service.get_order_for_user(session, user, order_id)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(order_id: int, user: User = Depends(require_role("customer")),
                       session: AsyncSession = Depends(get_db)):
    return await service.cancel_by_customer(session, user, order_id)


@router.post("/{order_id}/accept", response_model=OrderRead)
async def accept_order(order_id: int, user: User = Depends(require_role("restaurant", "admin")),
                       session: AsyncSession = Depends(get_db)):
    return await service.accept_by_restaurant(session, user, order_id)


@router.post("/{order_id}/reject", response_model=OrderRead)
async def reject_order(order_id: int, body: RejectBody = RejectBody(),
                       user: User = Depends(require_role("restaurant", "admin")),
                       session: AsyncSession = Depends(get_db)):
    return await service.reject_by_restaurant(session, user, order_id, body.reason)


@router.post("/{order_id}/status", response_model=OrderRead)
async def set_status(order_id: int, body: StatusBody,
                     user: User = Depends(require_role("restaurant", "admin")),
                     session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.advance_status(session, user, order_id, body.to, redis=redis)


@router.post("/internal/expire-acceptances")
async def expire_acceptances(user: User = Depends(require_role("admin")),
                             session: AsyncSession = Depends(get_db)):
    count = await service.expire_pending_acceptances(session, now=datetime.now(timezone.utc))
    return {"expired": count}

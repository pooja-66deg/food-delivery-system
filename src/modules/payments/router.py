"""HTTP routes for the payments domain."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.infrastructure.database import get_db
from src.modules.orders import service as order_service
from src.modules.payments import service as payment_service
from src.modules.payments.schemas import PaymentRead
from src.modules.users.dependencies import get_current_user, require_role
from src.modules.users.models import User

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentRead])
async def my_payment_history(
    limit: int = 50, offset: int = 0,
    user: User = Depends(require_role("customer")),
    session: AsyncSession = Depends(get_db),
):
    return await payment_service.list_for_customer(session, user.id, limit, offset)


@router.get("/order/{order_id}", response_model=PaymentRead)
async def get_order_payment(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Reuse the order's access check (customer / owning restaurant / admin).
    await order_service.get_order_for_user(session, user, order_id)
    payment = await payment_service.get_payment(session, order_id)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment


@router.post("/order/{order_id}/retry", response_model=PaymentRead)
async def retry_order_payment(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order_for_user(session, user, order_id)
    payment = await payment_service.retry_payment(session, order)
    if payment is None:
        raise NotFoundException("Payment", str(order_id))
    return payment

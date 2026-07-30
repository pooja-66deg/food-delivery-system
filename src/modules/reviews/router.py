"""HTTP routes for the reviews domain."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.modules.reviews import service
from src.modules.reviews.schemas import ReviewCreate, ReviewRead
from src.modules.users.dependencies import require_role
from src.modules.users.models import User

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    data: ReviewCreate,
    user: User = Depends(require_role("customer")),
    session: AsyncSession = Depends(get_db),
):
    return await service.create_review(session, user, data.order_id, data.rating, data.comment)


@router.get("/restaurant/{restaurant_id}", response_model=list[ReviewRead])
async def list_restaurant_reviews(restaurant_id: int, session: AsyncSession = Depends(get_db)):
    return await service.list_for_restaurant(session, restaurant_id)

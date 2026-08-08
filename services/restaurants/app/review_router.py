"""HTTP routes for the reviews domain."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app import reviews as service
from app.review_schemas import (
    ReviewCreate,
    ReviewRead,
    ReviewReply,
    ReviewUpdate,
)
from app.auth import auth
from shared.identity import Identity

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    data: ReviewCreate,
    user: Identity = Depends(auth.require_role("customer")),
    session: AsyncSession = Depends(get_db),
):
    return await service.create_review(session, user, data.order_id, data.rating, data.comment)


@router.get("/restaurant/{restaurant_id}", response_model=list[ReviewRead])
async def list_restaurant_reviews(
    restaurant_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    # Public: a rating is part of choosing a restaurant, so it must not need a login.
    return await service.list_for_restaurant(session, restaurant_id, limit, offset)


@router.patch("/{review_id}", response_model=ReviewRead)
async def update_review(
    review_id: int,
    data: ReviewUpdate,
    user: Identity = Depends(auth.require_role("customer")),
    session: AsyncSession = Depends(get_db),
):
    """Revise your own review. Only the author may edit."""
    return await service.update_review(
        session, user, review_id, data.rating, data.comment,
        # "comment" absent means leave it; present-and-null means clear it.
        comment_set="comment" in data.model_fields_set,
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: int,
    # Any authenticated role reaches the handler; the service allows the author
    # or an admin and rejects everyone else.
    user: Identity = Depends(auth.identity()),
    session: AsyncSession = Depends(get_db),
):
    await service.delete_review(session, user, review_id)


@router.post("/{review_id}/reply", response_model=ReviewRead)
async def reply_to_review(
    review_id: int,
    data: ReviewReply,
    user: Identity = Depends(auth.require_role("restaurant", "admin")),
    session: AsyncSession = Depends(get_db),
):
    """Answer a review of your restaurant. Replying again replaces the answer."""
    return await service.reply_to_review(session, user, review_id, data.reply)

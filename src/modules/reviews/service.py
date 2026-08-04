"""Review creation (customer rates a completed order) + owner notification."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException
from src.modules.notifications import service as notification_service
from src.modules.orders import service as order_service
from src.modules.orders.models import OrderStatus
from src.modules.restaurants.models import Restaurant
from src.modules.reviews.models import Review
from src.modules.users.models import User

_REVIEWABLE = (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value)


async def create_review(session: AsyncSession, user, order_id: int, rating: int, comment: str | None) -> Review:
    # Access check (404 if not visible / 403 otherwise), then customer-only.
    order = await order_service.get_order_for_user(session, user, order_id)
    if order.customer_id != user.id:
        raise ForbiddenException("Only the order's customer can review it")
    if order.status not in _REVIEWABLE:
        raise ConflictException("You can review an order once it has been delivered")
    if await session.scalar(select(Review).where(Review.order_id == order_id)) is not None:
        raise ConflictException("This order has already been reviewed")

    review = Review(order_id=order_id, customer_id=user.id, restaurant_id=order.restaurant_id,
                    rating=rating, comment=comment)
    session.add(review)

    # Notify the restaurant owner (in the same transaction).
    restaurant = await session.get(Restaurant, order.restaurant_id)
    if restaurant is not None:
        notification_service.add_notification(
            session, restaurant.owner_id, "review.created",
            f"New {rating}★ review on order #{order_id}.", order_id,
        )
    await session.commit()
    await session.refresh(review)
    return review


def display_name(first_name: str | None, last_name: str | None) -> str:
    """A reviewer's public name: first name plus last initial, "Alex R.".

    One helper so the format cannot drift between call sites. A missing last
    name degrades to the first name rather than leaving a stray full stop.
    """
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first:
        return ""
    return f"{first} {last[0]}." if last else first


async def list_for_restaurant(
    session: AsyncSession, restaurant_id: int, limit: int = 50, offset: int = 0
) -> list[Review]:
    """Public review list, newest first, with each reviewer's display name.

    The name is joined in rather than fetched per review, and attached to the
    returned objects for the response schema to read.
    """
    stmt = (
        select(Review, User.first_name, User.last_name)
        .join(User, User.id == Review.customer_id)
        .where(Review.restaurant_id == restaurant_id)
        .order_by(Review.id.desc())
        .limit(limit).offset(offset)
    )
    reviews = []
    for review, first_name, last_name in await session.execute(stmt):
        review.reviewer_name = display_name(first_name, last_name)
        reviews.append(review)
    return reviews

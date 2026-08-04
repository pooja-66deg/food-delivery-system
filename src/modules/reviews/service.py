"""Reviews: a customer rates a delivered order, edits or deletes it, and the
restaurant owner may answer once."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.modules.notifications import service as notification_service
from src.modules.orders import service as order_service
from src.modules.orders.models import OrderStatus
from src.modules.restaurants.models import Restaurant
from src.modules.reviews.models import Review
from src.modules.users.models import User

_REVIEWABLE = (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get(session: AsyncSession, review_id: int) -> Review:
    review = await session.get(Review, review_id)
    if review is None:
        raise NotFoundException("Review", str(review_id))
    return review


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
    return await _with_reviewer_name(session, review)


async def update_review(
    session: AsyncSession, user, review_id: int, rating: int | None, comment: str | None,
    comment_set: bool = False,
) -> Review:
    """Let the author revise their own review.

    Only the author — not an admin, who can delete a review but has no business
    rewriting one in a customer's name. ``comment_set`` distinguishes "leave the
    comment alone" from "clear it", which a bare None cannot express.
    """
    review = await _get(session, review_id)
    if review.customer_id != user.id:
        raise ForbiddenException("Only the review's author can edit it")

    if rating is not None:
        review.rating = rating
    if comment_set:
        review.comment = comment
    # Stamped only on a real edit, so "(edited)" in the UI means what it says.
    review.updated_at = _now()
    await session.commit()
    await session.refresh(review)
    return await _with_reviewer_name(session, review)


async def delete_review(session: AsyncSession, user, review_id: int) -> None:
    """Remove a review. The author may withdraw theirs; an admin may moderate any.

    A restaurant owner deliberately cannot: deleting criticism of your own
    business is exactly what a rating would need to be trustworthy.
    """
    review = await _get(session, review_id)
    if review.customer_id != user.id and user.role != "admin":
        raise ForbiddenException("Only the author or an admin can delete a review")
    await session.delete(review)
    await session.commit()


async def reply_to_review(session: AsyncSession, user, review_id: int, reply: str) -> Review:
    """Record the restaurant's public answer to a review.

    Restricted to the owner of the reviewed restaurant (or an admin) by the same
    ownership check the menu uses. Replying again replaces the previous answer —
    an owner correcting their wording should not produce two replies.
    """
    review = await _get(session, review_id)
    # Raises 403/404 unless this user manages that restaurant.
    from src.modules.restaurants import service as restaurant_service
    await restaurant_service.owned_restaurant(session, user, review.restaurant_id)

    review.owner_reply = reply
    review.owner_replied_at = _now()

    notification_service.add_notification(
        session, review.customer_id, "review.replied",
        f"The restaurant replied to your review of order #{review.order_id}.",
        review.order_id,
    )
    await session.commit()
    await session.refresh(review)
    return await _with_reviewer_name(session, review)


async def _with_reviewer_name(session: AsyncSession, review: Review) -> Review:
    """Attach the public reviewer name the read schema expects.

    The list endpoint joins it in; a single-review response has to fetch it, and
    doing that here keeps every path returning the same shape.
    """
    customer = await session.get(User, review.customer_id)
    review.reviewer_name = (
        display_name(customer.first_name, customer.last_name) if customer else ""
    )
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

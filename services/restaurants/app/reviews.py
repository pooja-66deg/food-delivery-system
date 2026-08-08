"""Reviews: a customer rates a delivered order, edits or deletes it, and the
restaurant owner may answer once.

Two things changed in the split.

**Eligibility.** The monolith asked the orders module whether the order was
visible to this user and had been delivered. Here that is answered from the local
``OrderSnapshot``, so posting a review does not depend on the orders service
being up. The snapshot lags by however long the event took to arrive — which
means a review may be refused for a few seconds after delivery, and the customer
retries. That is a much better failure than "reviews are down".

**Notifying the owner.** Was a direct write into the notifications table; now an
event, because that table belongs to another service.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import outbox
from app.models import OrderSnapshot, Restaurant, Review
from shared.errors import ConflictException, ForbiddenException, NotFoundException
from shared.identity import Identity

# Mirrors the orders service's DELIVERED / COMPLETED. Compared as strings
# because the enum lives in that service, and importing it would couple the two
# deployments over what is really just a pair of constants.
REVIEWABLE_STATUSES = ("DELIVERED", "COMPLETED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get(session: AsyncSession, review_id: int) -> Review:
    review = await session.get(Review, review_id)
    if review is None:
        raise NotFoundException("Review", str(review_id))
    return review


def _notify(session: AsyncSession, user_id: int, type_: str, message: str, order_id: int) -> None:
    """Queue an in-app notification for the notifications service."""
    outbox.record_event(
        session,
        "notification-events",
        str(order_id),
        {"user_id": user_id, "type": type_, "message": message, "order_id": order_id},
    )


async def create_review(
    session: AsyncSession, caller: Identity, order_id: int, rating: int, comment: str | None
) -> Review:
    snapshot = await session.get(OrderSnapshot, order_id)
    if snapshot is None:
        # Either no such order, or its event has not reached us yet. Both look
        # the same from here, and 404 is the honest answer to "review this
        # order" when we have never heard of it.
        raise NotFoundException("Order", str(order_id))
    if snapshot.customer_id != caller.user_id:
        raise ForbiddenException("Only the order's customer can review it")
    if snapshot.status not in REVIEWABLE_STATUSES:
        raise ConflictException("You can review an order once it has been delivered")
    if await session.scalar(select(Review).where(Review.order_id == order_id)) is not None:
        raise ConflictException("This order has already been reviewed")

    review = Review(
        order_id=order_id,
        customer_id=caller.user_id,
        restaurant_id=snapshot.restaurant_id,
        rating=rating,
        comment=comment,
        # Copied now, from the snapshot, so the byline survives without a users
        # table and reflects the name they reviewed under.
        reviewer_name=snapshot.customer_name,
    )
    session.add(review)

    restaurant = await session.get(Restaurant, snapshot.restaurant_id)
    if restaurant is not None:
        _notify(
            session,
            restaurant.owner_id,
            "review.created",
            f"New {rating}★ review on order #{order_id}.",
            order_id,
        )
    await session.commit()
    await session.refresh(review)
    return review


async def update_review(
    session: AsyncSession,
    caller: Identity,
    review_id: int,
    rating: int | None,
    comment: str | None,
    comment_set: bool = False,
) -> Review:
    """Let the author revise their own review.

    Only the author — not an admin, who can delete a review but has no business
    rewriting one in a customer's name. ``comment_set`` distinguishes "leave the
    comment alone" from "clear it", which a bare None cannot express.
    """
    review = await _get(session, review_id)
    if review.customer_id != caller.user_id:
        raise ForbiddenException("Only the review's author can edit it")

    if rating is not None:
        review.rating = rating
    if comment_set:
        review.comment = comment
    # Stamped only on a real edit, so "(edited)" in the UI means what it says.
    review.updated_at = _now()
    await session.commit()
    await session.refresh(review)
    return review


async def delete_review(session: AsyncSession, caller: Identity, review_id: int) -> None:
    """Remove a review. The author may withdraw theirs; an admin may moderate any.

    A restaurant owner deliberately cannot: deleting criticism of your own
    business is exactly what a rating would need to be trustworthy.
    """
    review = await _get(session, review_id)
    if review.customer_id != caller.user_id and caller.role != "admin":
        raise ForbiddenException("Only the author or an admin can delete a review")
    await session.delete(review)
    await session.commit()


async def reply_to_review(
    session: AsyncSession, caller: Identity, review_id: int, reply: str
) -> Review:
    """Record the restaurant's public answer to a review.

    Restricted to the owner of the reviewed restaurant (or an admin) by the same
    ownership check the menu uses — and that check is entirely local, because the
    restaurant row is in this database and the caller's id is in their token.

    Replying again replaces the previous answer: an owner correcting their
    wording should not produce two replies.
    """
    review = await _get(session, review_id)
    from app import service as restaurant_service

    await restaurant_service.owned_restaurant(session, caller, review.restaurant_id)

    review.owner_reply = reply
    review.owner_replied_at = _now()
    _notify(
        session,
        review.customer_id,
        "review.replied",
        f"The restaurant replied to your review of order #{review.order_id}.",
        review.order_id,
    )
    await session.commit()
    await session.refresh(review)
    return review


def display_name(first_name: str | None, last_name: str | None) -> str:
    """A reviewer's public name: first name plus last initial, "Alex R.".

    One helper so the format cannot drift between the place that builds it (the
    order snapshot) and anything that reads it. A missing last name degrades to
    the first name rather than leaving a stray full stop.
    """
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first:
        return ""
    return f"{first} {last[0]}." if last else first


async def list_for_restaurant(
    session: AsyncSession, restaurant_id: int, limit: int = 50, offset: int = 0
) -> list[Review]:
    """Public review list, newest first.

    No join any more: the reviewer's name is on the row. The monolith joined the
    users table for it, which is both impossible here and one fewer table to
    read on a page that renders on every restaurant view.
    """
    stmt = (
        select(Review)
        .where(Review.restaurant_id == restaurant_id)
        .order_by(Review.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt))

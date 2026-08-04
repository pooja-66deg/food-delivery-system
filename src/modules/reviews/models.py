"""Review model — a customer's rating of a completed order."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # The restaurant owner's public response. Null until they answer; editing an
    # existing reply overwrites it rather than threading, because a review is a
    # one-exchange affair and a thread invites an argument.
    owner_reply: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner_replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Set only when the author edits, so readers can be shown that a review
    # changed after the fact. Null means "never edited" — not "edited at
    # creation time", which is what defaulting to now() would imply.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

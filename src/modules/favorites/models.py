"""Favourite model — a customer's saved restaurant."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.adapters.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Favorite(Base):
    """One row per (user, restaurant) pair.

    The unique constraint is the whole correctness story: favouriting twice must
    not create a duplicate, and enforcing that in the database rather than by
    checking first means two concurrent taps cannot both slip through.
    """

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "restaurant_id", name="uq_favorite_user_restaurant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

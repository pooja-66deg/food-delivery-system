"""Schemas for the reviews domain."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    order_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    customer_id: int
    restaurant_id: int
    rating: int
    comment: str | None
    created_at: datetime
    # First name plus last initial — enough to read as a real person without
    # publishing a customer's full name. Empty when the account is gone.
    reviewer_name: str = ""

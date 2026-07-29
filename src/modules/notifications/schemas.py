"""Read schema for notifications."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: str
    type: str
    message: str
    order_id: int | None
    created_at: datetime

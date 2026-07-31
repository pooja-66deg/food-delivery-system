"""Read schema for deliveries."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    driver_id: int | None
    status: str
    assigned_at: datetime | None
    accepted_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None

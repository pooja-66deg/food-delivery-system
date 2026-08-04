"""Read schema for deliveries."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CoordinateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    latitude: float
    longitude: float


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
    # Where the driver is headed next, for navigation. Null when the restaurant
    # has no coordinates or the customer's address never geocoded.
    restaurant: CoordinateRead | None = None
    destination: CoordinateRead | None = None


class TrackingRead(BaseModel):
    """Everything the customer's tracking view needs, in one poll.

    Every geographic field is optional. A driver who has not shared a position,
    an ungeocoded address, or a restaurant without coordinates each yield null
    and a null ETA — states the UI renders honestly rather than faking.
    """

    order_id: int
    status: str
    driver_id: int | None
    driver: CoordinateRead | None = None
    restaurant: CoordinateRead | None = None
    destination: CoordinateRead | None = None
    eta_minutes: int | None = None
    distance_km: float | None = None
    eta_source: str | None = None  # "google" | "estimate" | None

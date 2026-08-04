"""Read/write schemas for notifications, channel preferences, and devices."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: str
    type: str
    message: str
    order_id: int | None
    created_at: datetime


class NotificationDeliveryRead(NotificationRead):
    """An outbound attempt, with whether the provider accepted it."""

    delivered: bool


class PreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    email_enabled: bool
    sms_enabled: bool
    push_enabled: bool


class PreferenceUpdate(BaseModel):
    """Channel opt-ins to change; omitted channels are left alone."""

    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    push_enabled: bool | None = None


class DeviceRegister(BaseModel):
    token: str = Field(..., min_length=8, max_length=255)
    platform: str = Field(default="web", max_length=20)


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # The token is what the caller sent us, so echoing it leaks nothing they do
    # not already hold — and they need it to unregister.
    token: str
    platform: str
    created_at: datetime

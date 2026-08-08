"""Read/write schemas for notifications, channel preferences, and devices —
plus the event contract this service consumes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderStatusEvent(BaseModel):
    """One order status change, as published by the orders service.

    This is a contract between two services that deploy separately, so it is
    additive-only: new fields must be optional, and no field may be removed or
    renamed without both sides shipping first. A consumer that cannot parse an
    event cannot handle it, and an unhandleable event is a lost notification.

    Carries a customer id, not an address. Where to send is this service's own
    business, resolved from its ``contacts`` read-model — so contact details
    live in one database instead of travelling on every order event and
    settling in everyone's.
    """

    order_id: int
    status: str
    customer_id: int


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

"""Read/response schemas for the orders domain."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    menu_item_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    actor: str
    reason: str | None
    at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    restaurant_id: int
    address_id: int
    status: str
    payment_method: str
    payment_status: str
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    refund_status: str
    refund_amount: Decimal
    cancelled_by: str | None
    cancel_reason: str | None
    created_at: datetime
    items: list[OrderItemRead]
    events: list[OrderStatusEventRead]


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    restaurant_id: int
    status: str
    total: Decimal
    created_at: datetime

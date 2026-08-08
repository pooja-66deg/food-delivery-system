"""Read schemas for the admin panel."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AdminStats(BaseModel):
    users: int
    restaurants: int
    orders_total: int
    orders_by_status: dict[str, int]
    gross_merchandise_value: Decimal  # sum of non-cancelled/non-rejected order totals


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    phone: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime


class AdminOrderRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    restaurant_id: int
    status: str
    payment_status: str
    total: Decimal
    created_at: datetime

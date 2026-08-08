"""Read schema for the payments domain."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    provider: str
    amount: Decimal
    status: str
    provider_ref: str | None
    created_at: datetime
    # Only ever set by the resume endpoint, for a card payment still awaiting
    # the customer. Never stored.
    checkout_url: str | None = None

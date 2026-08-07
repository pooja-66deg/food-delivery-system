"""Base event models and schemas for cross-service communication."""
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class BaseEvent(BaseModel):
    """Base class for all cross-service domain events.

    Every event has a unique ID, timestamp, source service identifier, and type.
    The data field carries domain-specific payload.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_service: str  # "orders", "payments", "delivery", etc.
    event_type: str  # "order.created", "payment.completed", etc.
    data: dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-15T10:30:00Z",
                "source_service": "orders",
                "event_type": "order.created",
                "data": {"order_id": "123", "user_id": "456"}
            }
        }

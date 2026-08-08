"""Tests for the BaseEvent model and event infrastructure."""
from datetime import datetime, timezone
import pytest
from src.shared.events import BaseEvent


class TestBaseEvent:
    """Test suite for BaseEvent model."""

    def test_event_creation_with_all_fields(self):
        """Test creating an event with all fields specified."""
        now = datetime.now(timezone.utc)
        event = BaseEvent(
            id="test-1",
            timestamp=now,
            source_service="orders",
            event_type="order.created",
            data={"order_id": "123", "user_id": "456"}
        )

        assert event.id == "test-1"
        assert event.timestamp == now
        assert event.source_service == "orders"
        assert event.event_type == "order.created"
        assert event.data == {"order_id": "123", "user_id": "456"}

    def test_event_auto_generates_id(self):
        """Test that BaseEvent auto-generates an ID if not provided."""
        event = BaseEvent(
            source_service="payments",
            event_type="payment.completed",
            data={"payment_id": "789"}
        )

        assert event.id is not None
        assert len(event.id) > 0
        # UUID string format validation
        assert len(event.id) == 36  # Standard UUID string length

    def test_event_auto_generates_timestamp(self):
        """Test that BaseEvent auto-generates a timestamp if not provided."""
        before = datetime.now(timezone.utc)
        event = BaseEvent(
            id="test-2",
            source_service="delivery",
            event_type="delivery.started",
            data={"delivery_id": "999"}
        )
        after = datetime.now(timezone.utc)

        assert event.timestamp is not None
        assert before <= event.timestamp <= after

    def test_event_serialization(self):
        """Test that BaseEvent can be serialized to JSON."""
        event = BaseEvent(
            id="test-3",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            source_service="users",
            event_type="user.registered",
            data={"user_id": "100", "email": "user@example.com"}
        )

        # Test model_dump (Pydantic v2)
        event_dict = event.model_dump()
        assert event_dict["id"] == "test-3"
        assert event_dict["source_service"] == "users"
        assert event_dict["event_type"] == "user.registered"
        assert event_dict["data"] == {"user_id": "100", "email": "user@example.com"}

    def test_event_with_complex_data(self):
        """Test that BaseEvent can handle complex nested data."""
        complex_data = {
            "order_id": "123",
            "items": [
                {"item_id": "1", "quantity": 2, "price": 10.50},
                {"item_id": "2", "quantity": 1, "price": 25.00}
            ],
            "metadata": {
                "created_at": "2024-01-15T10:30:00Z",
                "source": "web"
            }
        }
        event = BaseEvent(
            id="test-4",
            source_service="orders",
            event_type="order.placed",
            data=complex_data
        )

        assert event.data == complex_data
        assert event.data["items"][0]["quantity"] == 2
        assert event.data["metadata"]["source"] == "web"

    def test_event_uniqueness(self):
        """Test that auto-generated IDs are unique across events."""
        events = [
            BaseEvent(
                source_service="orders",
                event_type="order.created",
                data={}
            )
            for _ in range(5)
        ]

        ids = [event.id for event in events]
        assert len(ids) == len(set(ids)), "Event IDs should be unique"

    def test_event_with_empty_data(self):
        """Test creating an event with empty data dictionary."""
        event = BaseEvent(
            id="test-5",
            source_service="test",
            event_type="test.event",
            data={}
        )

        assert event.data == {}

    def test_event_model_dump_json(self):
        """Test that BaseEvent can be dumped as JSON string."""
        event = BaseEvent(
            id="test-6",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            source_service="orders",
            event_type="order.shipped",
            data={"order_id": "123", "carrier": "FedEx"}
        )

        # Test model_dump_json
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        assert "test-6" in json_str
        assert "order.shipped" in json_str
        assert "orders" in json_str

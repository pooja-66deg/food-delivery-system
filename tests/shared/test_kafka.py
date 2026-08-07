"""Tests for Kafka producer and consumer infrastructure."""
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pytest
from kafka.errors import KafkaError

from src.shared.events import BaseEvent
from src.shared.kafka_producer import KafkaProducer


class TestKafkaProducer:
    """Test suite for KafkaProducer."""

    @pytest.fixture
    def mock_kafka_producer(self):
        """Mock KafkaProducer for testing."""
        with patch("src.shared.kafka_producer._KafkaProducer") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_producer_publishes_event(self, mock_kafka_producer):
        """Test that KafkaProducer successfully publishes an event to Kafka."""
        # Set up mock
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        # Create producer and event
        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        event = BaseEvent(
            id="test-1",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            source_service="orders",
            event_type="order.created",
            data={"order_id": "123", "user_id": "456"}
        )

        # Publish event
        await producer.publish(event)

        # Verify the producer.send was called with correct topic
        mock_producer_instance.send.assert_called_once()
        call_args = mock_producer_instance.send.call_args

        # Check topic is event_type
        assert call_args.kwargs["topic"] == "order.created"
        # Check key is event ID
        assert call_args.kwargs["key"] == b"test-1"
        # Check value contains event data
        assert call_args.kwargs["value"]["id"] == "test-1"
        assert call_args.kwargs["value"]["source_service"] == "orders"

    @pytest.mark.asyncio
    async def test_producer_publishes_to_correct_topic(self, mock_kafka_producer):
        """Test that the event is published to the correct topic based on event_type."""
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")

        # Test different event types map to different topics
        event_types = [
            "order.created",
            "payment.completed",
            "delivery.started",
            "user.registered"
        ]

        for event_type in event_types:
            mock_producer_instance.reset_mock()
            event = BaseEvent(
                id="test-event",
                source_service="test",
                event_type=event_type,
                data={}
            )
            await producer.publish(event)

            call_args = mock_producer_instance.send.call_args
            assert call_args.kwargs["topic"] == event_type

    @pytest.mark.asyncio
    async def test_producer_closes_properly(self, mock_kafka_producer):
        """Test that KafkaProducer closes the underlying Kafka producer."""
        mock_producer_instance = MagicMock()
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        producer.close()

        mock_producer_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_producer_handles_kafka_error(self, mock_kafka_producer):
        """Test that KafkaProducer properly handles Kafka errors."""
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        # Simulate KafkaError on get
        mock_future.get.side_effect = KafkaError("Kafka broker not available")
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        event = BaseEvent(
            id="test-error",
            source_service="orders",
            event_type="order.created",
            data={}
        )

        # Should raise KafkaError
        with pytest.raises(KafkaError):
            await producer.publish(event)

    @pytest.mark.asyncio
    async def test_producer_uses_event_id_as_key(self, mock_kafka_producer):
        """Test that the event ID is used as the partition key."""
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        event_id = "unique-event-id-12345"
        event = BaseEvent(
            id=event_id,
            source_service="orders",
            event_type="order.created",
            data={}
        )

        await producer.publish(event)

        call_args = mock_producer_instance.send.call_args
        assert call_args.kwargs["key"] == event_id.encode("utf-8")

    @pytest.mark.asyncio
    async def test_producer_serializes_event_data(self, mock_kafka_producer):
        """Test that event data is properly serialized in the Kafka message."""
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = None
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        event_data = {
            "order_id": "123",
            "items": [{"id": "item1", "qty": 2}],
            "total": 99.99
        }
        event = BaseEvent(
            id="test-serialize",
            source_service="orders",
            event_type="order.created",
            data=event_data
        )

        await producer.publish(event)

        call_args = mock_producer_instance.send.call_args
        sent_value = call_args.kwargs["value"]

        assert sent_value["data"] == event_data
        assert sent_value["data"]["order_id"] == "123"
        assert sent_value["data"]["items"][0]["qty"] == 2

    def test_producer_initialization_with_custom_bootstrap_servers(self, mock_kafka_producer):
        """Test that KafkaProducer accepts custom bootstrap servers."""
        custom_servers = "kafka1:9092,kafka2:9092,kafka3:9092"
        producer = KafkaProducer(bootstrap_servers=custom_servers)

        # Verify KafkaProducer was initialized with custom servers
        mock_kafka_producer.assert_called_once()
        call_kwargs = mock_kafka_producer.call_args[1]
        assert call_kwargs["bootstrap_servers"] == custom_servers

    def test_producer_initialization_defaults(self, mock_kafka_producer):
        """Test that KafkaProducer uses default bootstrap servers if not specified."""
        producer = KafkaProducer()

        # Verify KafkaProducer was initialized with default servers
        mock_kafka_producer.assert_called_once()
        call_kwargs = mock_kafka_producer.call_args[1]
        assert call_kwargs["bootstrap_servers"] == "kafka:9092"

    @pytest.mark.asyncio
    async def test_producer_generic_exception_handling(self, mock_kafka_producer):
        """Test that KafkaProducer handles non-Kafka exceptions."""
        mock_producer_instance = MagicMock()
        mock_future = MagicMock()
        # Simulate a generic exception
        mock_future.get.side_effect = RuntimeError("Unexpected error")
        mock_producer_instance.send.return_value = mock_future
        mock_kafka_producer.return_value = mock_producer_instance

        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        event = BaseEvent(
            id="test-generic-error",
            source_service="orders",
            event_type="order.created",
            data={}
        )

        # Should raise the RuntimeError
        with pytest.raises(RuntimeError):
            await producer.publish(event)

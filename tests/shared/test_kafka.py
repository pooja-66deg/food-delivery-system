"""Tests for Kafka producer and consumer infrastructure."""
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pytest
from kafka.errors import KafkaError

from src.shared.events import BaseEvent
from src.shared.kafka_producer import KafkaProducer
from src.shared.kafka_consumer import KafkaConsumer


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


class TestKafkaConsumer:
    """Test suite for KafkaConsumer."""

    def test_consumer_invokes_handle_on_message_received(self):
        """Test that KafkaConsumer calls handle() when a message is received."""
        # Create a test consumer implementation
        class TestConsumer(KafkaConsumer):
            def __init__(self, topics, **kwargs):
                # Don't call super().__init__ to avoid real Kafka connection
                self.topics = topics
                self.handled_events = []
                self.consumer = None

            def handle(self, event: BaseEvent) -> None:
                """Track events handled."""
                self.handled_events.append(event)

        # Create mock message
        mock_message = MagicMock()
        mock_message.value = {
            "id": "test-event-1",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "source_service": "orders",
            "event_type": "order.created",
            "data": {"order_id": "123"}
        }

        # Create consumer instance and mock the consumer
        consumer = TestConsumer(topics=["order.created"])
        consumer.consumer = MagicMock()
        # Simulate one message then StopIteration to exit run loop
        consumer.consumer.__iter__ = MagicMock(
            return_value=iter([mock_message])
        )

        # Call run (which should invoke handle)
        consumer.run()

        # Verify handle was invoked
        assert len(consumer.handled_events) == 1
        assert consumer.handled_events[0].id == "test-event-1"
        assert consumer.handled_events[0].source_service == "orders"
        assert consumer.handled_events[0].event_type == "order.created"
        assert consumer.handled_events[0].data["order_id"] == "123"

    def test_consumer_handle_receives_correct_event_data(self):
        """Test that handle() receives properly deserialized BaseEvent."""
        class TrackingConsumer(KafkaConsumer):
            def __init__(self, topics, **kwargs):
                self.topics = topics
                self.last_event = None
                self.consumer = None

            def handle(self, event: BaseEvent) -> None:
                self.last_event = event

        # Create mock message with complex data
        mock_message = MagicMock()
        complex_data = {
            "order_id": "456",
            "items": [
                {"id": "item1", "qty": 2, "price": 10.50},
                {"id": "item2", "qty": 1, "price": 25.00}
            ],
            "total": 45.50
        }
        mock_message.value = {
            "id": "complex-event",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "source_service": "orders",
            "event_type": "order.placed",
            "data": complex_data
        }

        consumer = TrackingConsumer(topics=["order.placed"])
        consumer.consumer = MagicMock()
        consumer.consumer.__iter__ = MagicMock(
            return_value=iter([mock_message])
        )

        consumer.run()

        # Verify event was properly deserialized
        assert consumer.last_event is not None
        assert isinstance(consumer.last_event, BaseEvent)
        assert consumer.last_event.id == "complex-event"
        assert consumer.last_event.data == complex_data
        assert consumer.last_event.data["items"][0]["qty"] == 2

    def test_consumer_handles_multiple_messages(self):
        """Test that KafkaConsumer processes multiple messages sequentially."""
        class CountingConsumer(KafkaConsumer):
            def __init__(self, topics, **kwargs):
                self.topics = topics
                self.event_count = 0
                self.consumer = None

            def handle(self, event: BaseEvent) -> None:
                self.event_count += 1

        # Create multiple mock messages
        messages = [
            MagicMock(value={
                "id": f"event-{i}",
                "timestamp": "2024-01-15T10:30:00+00:00",
                "source_service": "orders",
                "event_type": "order.created",
                "data": {"order_id": str(i)}
            })
            for i in range(3)
        ]

        consumer = CountingConsumer(topics=["order.created"])
        consumer.consumer = MagicMock()
        consumer.consumer.__iter__ = MagicMock(return_value=iter(messages))

        consumer.run()

        # Verify all messages were handled
        assert consumer.event_count == 3

    def test_consumer_continues_on_message_error(self):
        """Test that consumer continues processing after error in a message."""
        class RobustConsumer(KafkaConsumer):
            def __init__(self, topics, **kwargs):
                self.topics = topics
                self.successful_events = []
                self.consumer = None

            def handle(self, event: BaseEvent) -> None:
                self.successful_events.append(event.id)

        # Create messages, where one has invalid data
        valid_message1 = MagicMock(value={
            "id": "event-1",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "source_service": "orders",
            "event_type": "order.created",
            "data": {}
        })

        invalid_message = MagicMock(value=None)

        valid_message2 = MagicMock(value={
            "id": "event-2",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "source_service": "orders",
            "event_type": "order.created",
            "data": {}
        })

        consumer = RobustConsumer(topics=["order.created"])
        consumer.consumer = MagicMock()
        consumer.consumer.__iter__ = MagicMock(
            return_value=iter([valid_message1, invalid_message, valid_message2])
        )

        # Run without raising an exception
        consumer.run()

        # Verify valid messages were processed despite error
        assert len(consumer.successful_events) == 2
        assert "event-1" in consumer.successful_events
        assert "event-2" in consumer.successful_events

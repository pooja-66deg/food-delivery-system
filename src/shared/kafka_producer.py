"""Kafka producer for publishing domain events to topics."""
import json
import logging
from typing import Optional
from kafka import KafkaProducer as _KafkaProducer
from kafka.errors import KafkaError

from src.shared.events import BaseEvent

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Publishes domain events to Kafka topics for other services to consume.

    Each BaseEvent is serialized to JSON and published to a topic named after
    its event_type (e.g., "order.created" event goes to "order.created" topic).
    """

    def __init__(self, bootstrap_servers: str = "kafka:9092", **kwargs):
        """Initialize Kafka producer.

        Args:
            bootstrap_servers: Kafka broker address(es), comma-separated.
            **kwargs: Additional arguments passed to KafkaProducer.
        """
        self.producer = _KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            **kwargs
        )

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to its corresponding Kafka topic.

        The topic name is derived from the event_type (e.g., 'order.created').
        The event is serialized to JSON and published with its ID as the key
        (to ensure ordering of events from the same source).

        Args:
            event: The domain event to publish.

        Raises:
            KafkaError: If the publish fails.
        """
        try:
            # Use event ID as the partition key to ensure ordering
            future = self.producer.send(
                topic=event.event_type,
                key=event.id.encode("utf-8"),
                value=event.model_dump()
            )
            # Block until the message is delivered (with timeout)
            future.get(timeout=10)
            logger.info(f"Published event {event.id} to topic {event.event_type}")
        except KafkaError as e:
            logger.error(f"Failed to publish event {event.id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error publishing event {event.id}: {e}")
            raise

    def close(self) -> None:
        """Close the producer and clean up resources."""
        if self.producer:
            self.producer.close()

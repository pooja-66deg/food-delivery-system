"""Base Kafka consumer for handling domain events."""
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from kafka import KafkaConsumer as _KafkaConsumer
from kafka.errors import KafkaError

from .events import BaseEvent

logger = logging.getLogger(__name__)


class KafkaConsumer(ABC):
    """Abstract base class for Kafka consumers that handle domain events.

    Subclasses must implement the handle() method to define how they process
    events from their subscribed topics.
    """

    def __init__(
        self,
        topics: List[str],
        bootstrap_servers: str = "kafka:9092",
        group_id: Optional[str] = None,
        **kwargs
    ):
        """Initialize Kafka consumer.

        Args:
            topics: List of topic names to subscribe to.
            bootstrap_servers: Kafka broker address(es), comma-separated.
            group_id: Consumer group ID for coordinated consumption.
            **kwargs: Additional arguments passed to KafkaConsumer.
        """
        self.topics = topics
        self.consumer = _KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id or self.__class__.__name__,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            auto_offset_reset="earliest",
            **kwargs
        )

    @abstractmethod
    def handle(self, event: BaseEvent) -> None:
        """Handle a received event.

        This method should be overridden by subclasses to implement
        domain-specific event handling logic.

        Args:
            event: The domain event to handle.
        """
        pass

    def run(self) -> None:
        """Start consuming events from subscribed topics.

        This is a blocking call that will continuously consume and handle
        events from Kafka. Call from a separate thread or process.

        Raises:
            KafkaError: If there are issues with the Kafka connection.
        """
        try:
            logger.info(f"Starting consumer for topics: {self.topics}")
            for message in self.consumer:
                try:
                    if message.value:
                        event_data = message.value
                        event = BaseEvent(**event_data)
                        logger.info(f"Received event {event.id} of type {event.event_type}")
                        self.handle(event)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except KafkaError as e:
            logger.error(f"Kafka consumer error: {e}")
            raise
        finally:
            self.close()

    def close(self) -> None:
        """Close the consumer and clean up resources."""
        if self.consumer:
            self.consumer.close()

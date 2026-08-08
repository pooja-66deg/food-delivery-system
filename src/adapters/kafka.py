"""Kafka producer setup.

The producer is created lazily and its blocking calls are run in a thread pool
so they never stall the asyncio event loop. Startup does not hard-fail if the
broker is unreachable; ``send_event`` surfaces the error at publish time
instead, which keeps the API bootable in local/dev without Kafka running.
"""

import asyncio
import json
import logging
from typing import Optional

from kafka import KafkaProducer
from kafka.errors import KafkaError

from src.config import settings

logger = logging.getLogger(__name__)

producer: Optional[KafkaProducer] = None


def is_configured() -> bool:
    """Whether Kafka is switched on at all (e.g. KAFKA_BROKERS=disabled turns it off).

    Distinct from "the broker is reachable": a configured-but-down broker is a
    failure worth retrying, whereas a deliberately disabled one means nothing
    should be trying to publish in the first place. The outbox relay needs to
    tell those apart — see ``src.modules.events.relay``.
    """
    host = settings.kafka_brokers.split(":")[0].strip().lower()
    return bool(settings.kafka_brokers) and host not in ("", "disabled", "none", "off")


def init_kafka() -> None:
    """Initialize the Kafka producer.

    Connection errors are logged rather than raised so the application can start
    even when the broker is temporarily unavailable.
    """
    global producer
    # Allow explicitly turning Kafka off (e.g. KAFKA_BROKERS=disabled) so local
    # setups without a broker start cleanly instead of logging connection errors.
    if not is_configured():
        producer = None
        logger.info("Kafka disabled (KAFKA_BROKERS=%s); event publishing is off.", settings.kafka_brokers)
        return

    try:
        producer = KafkaProducer(
            bootstrap_servers=settings.kafka_brokers.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
            acks="all",
            retries=3,
        )
        logger.info("Kafka producer initialized")
    except KafkaError as exc:
        producer = None
        logger.error("Kafka producer initialization failed: %s", exc)


async def send_event(topic: str, key: str, value: dict) -> None:
    """Publish an event to a Kafka topic.

    The kafka-python client is synchronous, so the blocking send/flush is
    delegated to a worker thread to avoid blocking the event loop.
    """
    if producer is None:
        raise RuntimeError("Kafka producer not initialized")

    def _send() -> None:
        future = producer.send(topic, key=key, value=value)
        metadata = future.get(timeout=10)
        logger.info(
            "Event sent to %s partition %s offset %s",
            metadata.topic,
            metadata.partition,
            metadata.offset,
        )

    try:
        await asyncio.to_thread(_send)
    except KafkaError as exc:
        logger.error("Failed to send event to Kafka: %s", exc)
        raise


def close_kafka() -> None:
    """Flush and close the Kafka producer."""
    global producer
    if producer is not None:
        producer.flush()
        producer.close()
        producer = None
        logger.info("Kafka producer closed")

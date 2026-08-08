"""Publishing and subscribing, once, behind one interface.

Two reasons this module exists.

**The transport differs by environment.** Locally there is a Kafka container, and
that is the right thing for development: no cloud credentials, no billing, and a
developer can read the topic with a shell command. On GCP there is no managed
Kafka worth its fixed cost at this size, so production uses Pub/Sub. Neither
choice should be visible in a service's business logic, so neither is.

**The poll loop was written six times.** Every service had its own copy of the
same thread, the same offset handling, the same "commit only after the handler
returned" rule. Six copies of a concurrency-sensitive loop is six places for the
same subtle bug, and it had already drifted between them.

A service now supplies only what is actually its own: which topics it cares about
and what to do with each. The delivery semantics are the same everywhere:

- at-least-once, biased towards repeating rather than dropping;
- the offset (or ack) moves only after the handler has committed;
- a handler that raises leaves the message unacknowledged for redelivery, except
  for a message that cannot be parsed at all, which is acknowledged and skipped
  so one bad payload cannot stop a topic forever.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Awaitable, Callable, Optional, Protocol

logger = logging.getLogger(__name__)

#: ``(session, payload) -> None``. Raising means "redeliver this".
Handler = Callable[[Any, dict], Awaitable[None]]


def unwrap(value: dict) -> dict:
    """Take the payload out of an envelope, if there is one.

    Publishers may wrap payloads as ``{id, event_type, data}``; simpler ones send
    the payload flat. Accepting both keeps an envelope change on the publishing
    side from silently freezing a consumer.
    """
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        return value["data"]
    return value


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------


class Publisher(Protocol):
    async def publish(self, topic: str, key: Optional[str], value: dict) -> None: ...

    def close(self) -> None: ...


class KafkaPublisher:
    """kafka-python, for local development.

    A blocking client, so the send runs in a worker thread: a publisher that
    blocked the event loop for its broker timeout would stall every request the
    service is serving.
    """

    def __init__(self, bootstrap_servers: str, timeout_seconds: int = 10):
        from kafka import KafkaProducer

        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
            acks="all",
            retries=3,
        )
        self._timeout = timeout_seconds

    async def publish(self, topic: str, key: Optional[str], value: dict) -> None:
        def _send() -> None:
            self._producer.send(topic, key=key, value=value).get(timeout=self._timeout)

        await asyncio.to_thread(_send)

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()


class PubSubPublisher:
    """Google Cloud Pub/Sub, for production.

    The key becomes an ordering key, which is Pub/Sub's equivalent of a Kafka
    partition key: messages sharing one are delivered in order. It matters for
    the same reason it did there — two status changes for the same order must not
    arrive backwards.
    """

    def __init__(self, project_id: str, timeout_seconds: int = 10):
        from google.cloud import pubsub_v1

        self._project = project_id
        self._timeout = timeout_seconds
        self._client = pubsub_v1.PublisherClient(
            publisher_options=pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
        )

    def _path(self, topic: str) -> str:
        return self._client.topic_path(self._project, topic)

    async def publish(self, topic: str, key: Optional[str], value: dict) -> None:
        data = json.dumps(value, default=str).encode("utf-8")

        def _send() -> None:
            future = self._client.publish(
                self._path(topic), data, ordering_key=key or ""
            )
            future.result(timeout=self._timeout)

        await asyncio.to_thread(_send)

    def close(self) -> None:
        self._client.stop()


def publisher_for(*, transport: str, kafka_servers: str, project_id: Optional[str]) -> Publisher:
    """The publisher this environment wants.

    ``transport`` is explicit rather than inferred from whether a project id
    happens to be set: a deploy that silently picked the wrong transport would
    look healthy and publish into the void.
    """
    if transport == "pubsub":
        if not project_id:
            raise RuntimeError("MESSAGING_TRANSPORT=pubsub needs GOOGLE_CLOUD_PROJECT")
        return PubSubPublisher(project_id)
    return KafkaPublisher(kafka_servers)


# --------------------------------------------------------------------------
# Subscribing
# --------------------------------------------------------------------------


class EventConsumer:
    """Runs one service's handlers against whichever transport is configured.

    Owns the thread so no service has to. The handlers run on the service's own
    event loop — they use its async database session — which is why each message
    hops back across with ``run_coroutine_threadsafe``.
    """

    def __init__(
        self,
        *,
        transport: str,
        topics: list[str],
        group: str,
        handlers: dict[str, Handler],
        session_factory,
        kafka_servers: str = "kafka:9092",
        project_id: Optional[str] = None,
        handler_timeout_seconds: int = 30,
    ):
        self._transport = transport
        self._topics = topics
        self._group = group
        self._handlers = handlers
        self._session_factory = session_factory
        self._kafka_servers = kafka_servers
        self._project_id = project_id
        self._timeout = handler_timeout_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    async def _dispatch(self, topic: str, payload: dict) -> None:
        handler = self._handlers.get(topic)
        if handler is None:
            return
        async with self._session_factory() as session:
            await handler(session, payload)

    def _handle(self, loop: asyncio.AbstractEventLoop, topic: str, raw: bytes) -> bool:
        """Run one message. True means "acknowledge", False means "redeliver"."""
        try:
            payload = unwrap(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            # Unparseable: acknowledged and skipped. Redelivering it forever
            # would stop every later message on the topic.
            logger.error("Skipping unparseable %s message: %s", topic, exc)
            return True

        try:
            asyncio.run_coroutine_threadsafe(
                self._dispatch(topic, payload), loop
            ).result(timeout=self._timeout)
            return True
        except Exception:  # noqa: BLE001 — redeliver rather than drop
            logger.exception("Failed to handle %s message", topic)
            return False

    # -- Kafka ------------------------------------------------------------

    def _run_kafka(self, loop: asyncio.AbstractEventLoop) -> None:
        from kafka import KafkaConsumer
        from kafka.errors import KafkaError

        try:
            consumer = KafkaConsumer(
                *self._topics,
                bootstrap_servers=self._kafka_servers,
                group_id=self._group,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                consumer_timeout_ms=1000,  # so _stop is checked about once a second
            )
        except KafkaError as exc:
            logger.error("Could not connect to Kafka: %s", exc)
            return

        logger.info("Consuming %s from Kafka %s", self._topics, self._kafka_servers)
        try:
            while not self._stop.is_set():
                for message in consumer:
                    if self._stop.is_set():
                        break
                    if not message.value:
                        consumer.commit()
                        continue
                    if self._handle(loop, message.topic, message.value):
                        consumer.commit()
        finally:
            consumer.close()

    # -- Pub/Sub ----------------------------------------------------------

    def _run_pubsub(self, loop: asyncio.AbstractEventLoop) -> None:
        from google.cloud import pubsub_v1

        client = pubsub_v1.SubscriberClient()
        logger.info("Consuming %s from Pub/Sub in %s", self._topics, self._project_id)

        futures = []
        for topic in self._topics:
            # One subscription per (service, topic). The name has to be stable
            # and derivable, because the deploy creates it and the service finds
            # it — see infra/gcp/cloudbuild.yaml.
            path = client.subscription_path(self._project_id, f"{self._group}--{topic}")

            def _callback(message, topic=topic):
                if self._handle(loop, topic, message.data):
                    message.ack()
                else:
                    # Nacked, so Pub/Sub redelivers after the backoff rather than
                    # waiting out the ack deadline.
                    message.nack()

            futures.append(client.subscribe(path, callback=_callback))

        try:
            while not self._stop.is_set():
                self._stop.wait(timeout=1)
        finally:
            for future in futures:
                future.cancel()
            client.close()

    # -- lifecycle --------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._stop.clear()
        target = self._run_pubsub if self._transport == "pubsub" else self._run_kafka
        self._thread = threading.Thread(
            target=target, args=(loop,), name="event-consumer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Consumer stopped")

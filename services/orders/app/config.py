"""Settings for the orders service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""


from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "orders-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-orders:5432/orders_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Every replica shares the group, so an event is handled once by the
    #: service rather than once per replica.
    kafka_group_id: str = "orders-service"
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "payment-events,delivery-events,address-events,restaurant-events,user-events"

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # The cart lives here, and the per-user checkout lock.
    redis_url: str = "redis://redis:6379/0"

    # The one service this one calls synchronously. Checkout cannot price an
    # order without it, and the customer is waiting — see app/clients.py.
    restaurants_service_url: str = "http://restaurants-service:8000"
    #: Small on purpose: a checkout that takes eight seconds has already failed
    #: as far as the customer is concerned.
    restaurants_timeout_seconds: float = 3.0
    breaker_threshold: int = 5
    breaker_cooldown_seconds: float = 10.0

    restaurant_accept_timeout_seconds: int = 300
    #: How long a card order may sit unpaid before it is cancelled and its stock
    #: reservation released.
    payment_window_seconds: int = 900

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

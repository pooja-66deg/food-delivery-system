"""Settings for the admin service.

Its own, not the monolith's. Note what is absent: no Stripe key, no Twilio
credentials, no database URL for anyone else's data. An operator console needs
to read, not to act on a payment provider.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "admin-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-admin:5432/admin_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_group_id: str = "admin-service"
    #: Everything, because an operator console reports on everything. This is
    #: the one service for which that is the right answer rather than a smell.
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "order-events,user-events,user-contact-events,restaurant-events"

    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # The one action the console takes rather than reports: running the
    # acceptance-timeout sweep, which belongs to the orders service.
    orders_service_url: str = "http://orders-service:8000"
    orders_timeout_seconds: float = 10.0
    breaker_threshold: int = 5
    breaker_cooldown_seconds: float = 10.0

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

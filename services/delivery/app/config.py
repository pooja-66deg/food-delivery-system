"""Settings for the delivery service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "delivery-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-delivery:5432/delivery_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Every replica shares the group, so an event is handled once by the
    #: service rather than once per replica.
    kafka_group_id: str = "delivery-service"
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "order-events,user-events,restaurant-events"

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Redis is shared infrastructure, not another service: driver positions
    # (GEO) and the ETA cache live here. Shared, but not a coupling to a team's
    # deploy — losing it degrades ETAs, it does not stop deliveries.
    redis_url: str = "redis://redis:6379/0"

    # Routes API for real ETAs. Unset: ETAs fall back to a straight-line
    # estimate, which is a working service rather than a broken one.
    google_maps_api_key: Optional[str] = None
    delivery_average_speed_kmh: float = 25.0
    #: How long a computed ETA is cached per order, so a 5s tracking poll does
    #: not hit the Routes API twelve times a minute.
    delivery_eta_cache_seconds: int = 30

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

"""Settings for the restaurants service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "restaurants-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-restaurants:5432/restaurants_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Every replica shares the group, so an event is handled once by the
    #: service rather than once per replica.
    kafka_group_id: str = "restaurants-service"
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "order-events"

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Images: local disk in development, a public GCS bucket in production.
    # Both return the same URL shape, so callers never know which is in use.
    media_root: str = "media"
    gcs_bucket_name: Optional[str] = None

    # Geocoding a restaurant's address, and the delivery-zone maths that uses
    # it. Unset: zones fall back to a city match, which is the pre-radius rule.
    google_maps_api_key: Optional[str] = None
    #: Enforced for a geocoded restaurant that has not set its own radius, in km.
    delivery_default_radius_km: float = 10.0
    delivery_average_speed_kmh: float = 25.0

    redis_url: Optional[str] = None

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

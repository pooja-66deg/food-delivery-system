"""Settings for the admin service.

Its own, not the monolith's. Note what is absent: no Stripe key, no Twilio
credentials, no database URL for anyone else's data. An operator console needs
to read, not to act on a payment provider.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.cors import split_origins


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

    # Pool size, per instance. Seven services share one Cloud SQL instance, so
    # the ceiling that matters is the sum across all of them times their replica
    # count — not what any one service would like for itself. Overridable so a
    # bigger tier does not need a code change.
    #: 2 + 1 = 3 per instance. Seven services at one replica each is 21, which
    #: fits under db-f1-micro's ~25 max_connections with room for the Cloud SQL
    #: proxy and a superuser slot. Raise these *and* the instance tier together —
    #: raising them alone is how the ceiling was breached in the first place.
    db_pool_size: int = 2
    db_max_overflow: int = 1

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
    # The users service, for bootstrapping the first admin.
    users_service_url: str = "http://users-service:8000"
    orders_timeout_seconds: float = 10.0
    breaker_threshold: int = 5
    breaker_cooldown_seconds: float = 10.0

    #: Origins the SPA is served from. The browser checks every response this
    #: service returns through the gateway against the page's origin, so this is
    #: needed here and not only in users — see shared/cors.py. Comma-separated
    #: because Cloud Run gives each service two hostnames.
    #:
    #: Deliberately never "*": these routes are called with credentials, and the
    #: two together are what allow any site to make authenticated requests on a
    #: signed-in visitor's behalf.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return split_origins(self.cors_origins)

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

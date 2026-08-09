"""Settings for the users service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "users-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-users:5432/users_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Every replica shares the group, so an event is handled once by the
    #: service rather than once per replica.
    kafka_group_id: str = "users-service"
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    #: restaurant-events carries an operator's approval decision back to the
    #: applicant's account — see app/consumer.py. This service publishes far more
    #: than it consumes, which is why the list is one topic long.
    kafka_topics: str = "restaurant-events"

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Auth rate limiting (fixed window, per client IP). This is the service
    # every credential-guessing attempt reaches, so the limits live here.
    auth_rate_max: int = 10
    auth_rate_window_seconds: int = 60

    #: Browser origins allowed to call this service, comma-separated.
    #:
    #: The frontend is a separate Cloud Run service on its own origin, so
    #: without this every browser request to a public auth route is rejected by
    #: the browser. Cloud Run serves each service on two hostnames, hence a list.
    #:
    #: Deliberately never "*": these routes are called with credentials, and the
    #: two together are what allow any site to make authenticated requests on a
    #: signed-in visitor's behalf.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # This service mints tokens as well as verifying them, so unlike the others
    # it needs the lifetimes too.
    jwt_expiration_minutes: int = 30
    jwt_refresh_expiration_days: int = 7

    # Redis holds the auth rate-limit counters, the single-use password-reset
    # tokens, and the revocation blocklist every other service reads. Shared
    # infrastructure, not another team's service.
    redis_url: str = "redis://redis:6379/0"

    #: How long an emailed reset link stays usable. Short on purpose: it is a
    #: bearer credential sitting in an inbox, and the person who asked for it is
    #: almost always looking at their mail right now.
    password_reset_ttl_seconds: int = 900
    #: Where the reset link points — the SPA, not this API. Unset in production
    #: and every reset email sends the recipient to their own machine.
    frontend_base_url: str = "http://localhost:5173"

    # Geocoding turns a new address into coordinates. Unset: addresses stay
    # ungeocoded, which degrades delivery-zone checks rather than breaking
    # registration.
    google_maps_api_key: Optional[str] = None
    delivery_average_speed_kmh: float = 25.0

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

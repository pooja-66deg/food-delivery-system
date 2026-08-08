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

    kafka_topics: str = ""

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Auth rate limiting (fixed window, per client IP). This is the service
    # every credential-guessing attempt reaches, so the limits live here.
    auth_rate_max: int = 10
    auth_rate_window_seconds: int = 60

    # This service mints tokens as well as verifying them, so unlike the others
    # it needs the lifetimes too.
    jwt_expiration_minutes: int = 30
    jwt_refresh_expiration_days: int = 7

    # Redis holds the OTP challenges, the single-use reset/verification tokens,
    # and the revocation blocklist every other service reads. Shared
    # infrastructure, not another team's service.
    redis_url: str = "redis://redis:6379/0"

    otp_length: int = 6
    otp_expiration_seconds: int = 120
    otp_max_attempts: int = 5
    otp_request_max: int = 3
    otp_request_window_seconds: int = 300
    password_reset_ttl_seconds: int = 900
    email_verification_ttl_seconds: int = 86400
    #: Where the reset / verification links point (the SPA, not this API).
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

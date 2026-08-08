"""Settings for the notifications service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — a database URL it must not use, a
Stripe key it has no business holding — and could not start without them. What
it reads here is exactly what it needs to run.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "notifications-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = "postgresql+asyncpg://fooduser:foodpass@postgres-notifications:5432/notifications_db"
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Consumer group. Every replica of this service shares it, so an event is
    #: handled once by the service rather than once per replica.
    kafka_group_id: str = "notifications-service"
    #: Topics this service subscribes to. It never calls the publishers back.
    #: Must match what orders actually publishes (see _emit_status) — a default
    #: that only works when compose overrides it is a service that is silently
    #: broken anywhere else.
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "order-events,notification-events,user-contact-events"

    # Only the signing secret, not the users database. Tokens are verified
    # locally — see shared/identity.py for why that matters.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Outbound providers. Absent means the sender logs instead of sending, which
    # is a working service, not a broken one.
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    sendgrid_from_email: Optional[str] = None
    fcm_server_key: Optional[str] = None

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

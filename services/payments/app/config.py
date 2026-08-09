"""Settings for the payments service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "payments-service"
    environment: str = "development"
    log_level: str = "INFO"

    #: This service's own database. Never another's, never the monolith's.
    database_url: str = (
        "postgresql+asyncpg://fooduser:foodpass@postgres-payments:5432/payments_db"
    )
    database_echo: bool = False

    kafka_bootstrap_servers: str = "kafka:9092"
    #: Every replica shares the group, so an event is handled once by the
    #: service rather than once per replica.
    kafka_group_id: str = "payments-service"
    # Which message transport this deployment uses. Explicit rather than
    # inferred from whether a project id happens to be set: a deploy that
    # silently picked the wrong one would look healthy and publish into the void.
    #: "kafka" (the compose stack) or "pubsub" (Cloud Run).
    messaging_transport: str = "kafka"
    google_cloud_project: Optional[str] = None

    kafka_topics: str = "order-events,payment-commands"

    # Only the signing secret, not the users database — see shared/identity.py.
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"

    # Redis carries the webhook replay-dedupe set. Shared infrastructure, not
    # another service.
    redis_url: str = "redis://redis:6379/0"

    # Stripe. Unset: the deterministic stand-in provider takes over, which is a
    # working service in dev rather than a broken one.
    stripe_secret_key: Optional[str] = None
    #: Signing secret for /payments/webhook. Without it no webhook can be
    #: verified, so none is trusted.
    stripe_webhook_secret: Optional[str] = None
    stripe_webhook_tolerance_seconds: int = 300
    #: ISO 4217 code the hosted checkout charges in. Settable rather than fixed
    #: because it has to match the currency the Stripe account can settle — a
    #: code the account does not support is rejected at session creation, so a
    #: wrong value fails the checkout outright rather than mispricing it.
    #:
    #: Assumed to be a two-decimal currency: see the ×100 in providers.py.
    stripe_currency: str = "inr"
    #: Where Stripe returns the customer after a hosted checkout.
    frontend_base_url: str = "http://localhost:5173"

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

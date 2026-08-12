"""Settings for the payments service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.cors import split_origins


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

    #: Origins the SPA is served from. The browser checks every response this
    #: service returns through the gateway against the page's origin, so this is
    #: needed here and not only in users — see shared/cors.py. Comma-separated
    #: because Cloud Run gives each service two hostnames.
    #:
    #: Deliberately never "*": these routes are called with credentials, and the
    #: two together are what allow any site to make authenticated requests on a
    #: signed-in visitor's behalf.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @field_validator("stripe_secret_key", "stripe_webhook_secret", mode="after")
    @classmethod
    def _strip_credential(cls, v: Optional[str]) -> Optional[str]:
        """Trim surrounding whitespace, and read blank as unset.

        A Secret Manager version written with ``echo`` instead of ``printf %s``
        carries a trailing newline. The value still looks correct everywhere it
        is displayed, but it is not a legal HTTP header value, so every Stripe
        call fails inside the SDK with "Invalid header value" — and because
        providers.py degrades a provider error to ok=False, checkout kept
        answering 200 while no card payment could be taken at all. That outage
        ran for over 20 hours in production on one newline.

        Blank collapses to None so a key that is set-but-empty selects the
        stand-in provider, which is a working service, rather than a Stripe
        client that cannot authenticate.
        """
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @property
    def cors_origin_list(self) -> list[str]:
        return split_origins(self.cors_origins)

    @property
    def topics(self) -> list[str]:
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]


settings = Settings()

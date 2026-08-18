"""Settings for the users service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config_guard import assert_production_secrets
from shared.cors import split_origins


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

    #: Shared password for the console's outer gate, checked by
    #: ``POST /auth/admin/gate``.
    #:
    #: It lives here rather than in the SPA because Vite inlines every ``VITE_``
    #: variable into the built bundle — a gate password held on the frontend is
    #: readable by anyone who opens the JavaScript, whether it was written as a
    #: literal or read from an environment variable. Only a value the browser
    #: never receives can gate anything.
    #:
    #: Unset means no gate, which is the local-development default. Production
    #: cannot leave it unset: see ``assert_production_secrets`` below.
    admin_gate_password: Optional[str] = None

    #: Required in the ``X-Bootstrap-Secret`` header by
    #: ``/auth/internal/bootstrap-admin``.
    #:
    #: That route creates the platform's first administrator and is reachable
    #: through the public gateway, so before this it was a race: whoever called
    #: it first owned the platform. Unset disables the route entirely rather than
    #: leaving it open — an unconfigured secret must not mean an unguarded door.
    bootstrap_secret: Optional[str] = None

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
        return split_origins(self.cors_origins)

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

# Import time, not startup: the process must die before it binds a port, so a
# deploy that dropped a secret fails visibly instead of serving on a public one.
assert_production_secrets(settings)

# The gate is off when unconfigured, which is right for a laptop and wrong for
# production: the console would then be reachable by anyone who guesses the URL,
# with nothing in front of the login form. Silently serving one fewer layer than
# the deployment intended is exactly the failure this file exists to prevent, so
# an unset gate password in production is a failed deploy rather than an open door.
if settings.environment == "production" and not settings.admin_gate_password:
    raise RuntimeError(
        "users-service refused to start in production:\n"
        "  - ADMIN_GATE_PASSWORD is unset, which disables the admin console gate.\n"
        "Set it from Secret Manager, or delete this check if the gate is being\n"
        "retired in favour of network-level access control (Cloud IAP, VPN)."
    )

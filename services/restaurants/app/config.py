"""Settings for the restaurants service.

Its own, not the monolith's. A service that read the platform's settings object
would need every variable the platform needs — including credentials it has no
business holding — and could not start without them.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.cors import split_origins


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

    #: order-events feeds review eligibility; user-events feeds the owner-name
    #: read-model the admin restaurant list reads.
    #: restaurant-registrations carries a new owner's venue across from the users
    #: service at sign-up — see service.register_from_signup for why it cannot
    #: simply be an API call.
    kafka_topics: str = "order-events,user-events,restaurant-registrations"

    #: Where "a restaurant is waiting for approval" is sent. An operations
    #: mailbox, not a user — this service has no idea who the admins are. Unset
    #: disables the alert and leaves the console as the way operators find
    #: pending venues.
    admin_alert_email: str = ""

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

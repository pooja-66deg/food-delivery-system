"""Configuration module for the Food Delivery Platform."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

_UNSET_CREDENTIALS = frozenset(
    {"", "-", "none", "null", "unset", "not-set", "not-configured", "changeme", "change-me"}
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_title: str = "Food Delivery Platform"
    api_version: str = "0.1.0"
    environment: str = "development"
    # Comma-separated list of allowed CORS origins (explicit — never "*" with credentials).
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Auth rate limiting (fixed window, per client IP)
    auth_rate_max: int = 10
    auth_rate_window_seconds: int = 60
    password_reset_ttl_seconds: int = 900
    email_verification_ttl_seconds: int = 86400
    # Base URL the reset / verification links point at (the SPA, not the API).
    frontend_base_url: str = "http://localhost:5173"

    # Database
    database_url: str
    database_echo: bool = False

    # Redis
    redis_url: str
    redis_cache_ttl: int = 3600

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30
    jwt_refresh_expiration_days: int = 7

    # OTP
    otp_length: int = 6
    otp_expiration_seconds: int = 120
    otp_max_attempts: int = 5
    otp_request_max: int = 3
    otp_request_window_seconds: int = 300

    # Orders
    restaurant_accept_timeout_seconds: int = 300
    # How long a card order may sit unpaid before it is cancelled and its stock
    # reservation released.
    payment_window_seconds: int = 900

    # Media (uploaded images)
    media_root: str = "media"

    # Google Cloud Storage (production only)
    gcs_bucket_name: Optional[str] = None

    # Kafka
    kafka_brokers: str = "localhost:9092"
    kafka_consumer_group: str = "food-delivery-group"

    # Outbox relay — the loop that publishes recorded events to Kafka.
    # Off only for tests and one-off scripts: with it off, events are still
    # recorded transactionally but never reach any consumer.
    outbox_relay_enabled: bool = True
    outbox_relay_interval_seconds: float = 1.0
    outbox_relay_batch_size: int = 100

    # Whether this process still sends the outbound (email/SMS/push) copies of
    # an order status change. Set false wherever the notifications service is
    # running, or the customer gets two of every message. Defaults true so a
    # deploy without the service behaves exactly as before.
    notifications_outbound_enabled: bool = True

    # Third-party Services
    stripe_api_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    # Signing secret for the /payments/webhook endpoint. Without it no webhook
    # can be verified, so none is trusted.
    stripe_webhook_secret: Optional[str] = None
    stripe_webhook_tolerance_seconds: int = 300
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    # Email (SendGrid) + Push (FCM) — optional; senders log when unset.
    sendgrid_api_key: Optional[str] = None
    sendgrid_from_email: Optional[str] = None
    fcm_server_key: Optional[str] = None
    # Google Maps (Routes API for ETAs, Geocoding API for addresses) — server
    # side only. Unset: ETAs fall back to a straight-line estimate and addresses
    # stay ungeocoded. The browser uses its own referrer-restricted key.
    google_maps_api_key: Optional[str] = None

    # Delivery zones
    # Radius enforced for a geocoded restaurant that has not set its own, in km.
    delivery_default_radius_km: float = 10.0

    # Delivery tracking
    # Assumed road speed for the fallback ETA, in km/h.
    delivery_average_speed_kmh: float = 25.0
    # How long a computed ETA is cached per order, so a 5s tracking poll does
    # not hit the Routes API twelve times a minute.
    delivery_eta_cache_seconds: int = 30

    # Logging
    log_level: str = "INFO"

    @field_validator("frontend_base_url", mode="before")
    @classmethod
    def _first_url_only(cls, value):
        """Keep a single URL even when handed a comma-separated list.

        The deploy sets this and CORS_ORIGINS from one substitution, and
        CORS_ORIGINS legitimately takes several origins. Emailed reset and
        verification links cannot: joining two URLs with a comma produces a dead
        link, and it would only be noticed by whoever clicked it. Take the first
        and drop any trailing slash.
        """
        if isinstance(value, str) and value.strip():
            return value.split(",")[0].strip().rstrip("/")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        """The CORS allowlist, normalised to what a browser actually sends.

        A browser's ``Origin`` header is scheme + host + optional port and never
        has a trailing slash, and CORSMiddleware compares it by exact string. So
        ``https://app.run.app/`` — which is what you get copying the URL out of an
        address bar — would match nothing and silently reject every request. Strip
        the slash here rather than relying on whoever sets the variable to know
        that. Duplicates are dropped while keeping the configured order.
        """
        seen: dict[str, None] = {}
        for origin in self.cors_origins.split(","):
            cleaned = origin.strip().rstrip("/")
            if cleaned:
                seen.setdefault(cleaned, None)
        return list(seen)

    @field_validator(
        "stripe_api_key", "stripe_secret_key", "stripe_webhook_secret",
        "twilio_account_sid", "twilio_auth_token", "twilio_phone_number",
        "sendgrid_api_key", "sendgrid_from_email", "fcm_server_key",
        "google_maps_api_key",
        mode="before",
    )
    @classmethod
    def _placeholder_credential_is_unset(cls, value):
        """Treat a blank or placeholder credential as absent.

        Each optional integration picks its provider by testing whether its key is
        truthy, so a deployment that writes ``not-configured`` into a secret would
        otherwise select the *live* provider and fail on every call. Normalising
        here means "unconfigured" is decided by one rule in one place instead of
        every call site having to recognise placeholder text.
        """
        if isinstance(value, str) and value.strip().lower() in _UNSET_CREDENTIALS:
            return None
        return value

    # extra="ignore": a `.env` holding a key this class does not declare — a stray
    # DB_PASSWORD, a note to self, a leftover from another tool — must not stop the
    # app from starting. The default (forbid) turns any such key into an import-time
    # crash, which is a lot of blast radius for something unrelated to the app.
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )


settings = Settings()

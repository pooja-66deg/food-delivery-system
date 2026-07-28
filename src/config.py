"""Configuration module for the Food Delivery Platform."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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

    # Kafka
    kafka_brokers: str = "localhost:9092"
    kafka_consumer_group: str = "food-delivery-group"

    # Third-party Services
    stripe_api_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()

"""Placeholder credentials must read as unset, not as live ones."""
import pytest
from pydantic import ValidationError

from src.config import Settings

_BASE = dict(
    database_url="postgresql://u:p@localhost:5432/db",
    redis_url="redis://localhost:6379/0",
    jwt_secret_key="test-key",
)


def _settings(**overrides) -> Settings:
    # _env_file=None so a developer's local .env cannot influence the result.
    return Settings(_env_file=None, **_BASE, **overrides)


@pytest.mark.parametrize(
    "placeholder",
    ["", "  ", "-", "none", "NONE", "null", "unset", "not-set",
     "not-configured", "NOT-CONFIGURED", "changeme", "change-me"],
)
def test_placeholder_google_key_reads_as_unset(placeholder):
    assert _settings(google_maps_api_key=placeholder).google_maps_api_key is None


def test_a_real_google_key_is_preserved():
    key = "AIzaSyExampleLookingKey123"
    assert _settings(google_maps_api_key=key).google_maps_api_key == key


def test_placeholder_google_key_selects_the_offline_providers():
    """The reason this validator exists: a truthy placeholder would select the
    live providers, and geocoding would then spend 8 seconds failing on every
    address save."""
    from src.modules.delivery import providers

    original = providers.settings.google_maps_api_key
    try:
        providers.settings.google_maps_api_key = _settings(
            google_maps_api_key="not-configured"
        ).google_maps_api_key
        assert isinstance(providers.routing_provider(), providers.HaversineRouting)
        assert isinstance(providers.geocode_provider(), providers.NullGeocoder)
    finally:
        providers.settings.google_maps_api_key = original


def test_placeholder_stripe_key_falls_back_to_the_stand_in():
    """Otherwise every card checkout would call Stripe with a bogus key and fail."""
    from src.modules.payments import providers

    original = providers.settings.stripe_secret_key
    try:
        providers.settings.stripe_secret_key = _settings(
            stripe_secret_key="not-configured"
        ).stripe_secret_key
        assert isinstance(providers.provider_for("CARD"), providers.CardProvider)

        providers.settings.stripe_secret_key = "sk_test_realkey"
        assert isinstance(providers.provider_for("CARD"), providers.StripeProvider)
    finally:
        providers.settings.stripe_secret_key = original


@pytest.mark.parametrize(
    "field",
    ["stripe_api_key", "stripe_secret_key", "stripe_webhook_secret",
     "twilio_account_sid", "twilio_auth_token", "twilio_phone_number",
     "sendgrid_api_key", "sendgrid_from_email", "fcm_server_key"],
)
def test_every_optional_credential_normalises(field):
    assert getattr(_settings(**{field: "not-configured"}), field) is None
    assert getattr(_settings(**{field: "real-value"}), field) == "real-value"


def test_an_unrelated_env_key_does_not_crash_startup():
    """A `.env` with a stray DB_PASSWORD used to fail validation at import time and
    take the whole build down with it."""
    assert Settings(_env_file=None, db_password="whatever", **_BASE).environment


def test_required_settings_are_still_required(monkeypatch):
    """Normalising placeholders must not have loosened the three that matter.

    The real environment has to be cleared as well as the file: ``_env_file=None``
    only silences `.env`, and the test runner exports these three.
    """
    for name in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

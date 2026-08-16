"""The startup check that stops a production service booting on dev defaults.

The failure this prevents is silent, which is why it is worth a test file: a
service that starts with ``dev-secret-change-me`` behaves perfectly — healthy
probes, valid tokens, clean logs — while anyone who has read this repository can
mint a token for any user id and any role in every service at once. Nothing
observable distinguishes that from a correct deployment.
"""

import pytest

from shared.config_guard import assert_production_secrets


class FakeSettings:
    """Only the four attributes the guard reads."""

    def __init__(
        self,
        environment="production",
        service_name="users-service",
        jwt_secret_key="dTgHkQ2wZ9pL4nR7vXbC1sYmE6uA3jF8oI0dKlPqWtNr",
        database_url="postgresql+asyncpg://fooduser:Str0ngP4ss@10.0.0.3:5432/users_db",
    ):
        self.environment = environment
        self.service_name = service_name
        self.jwt_secret_key = jwt_secret_key
        self.database_url = database_url


def test_a_correctly_configured_production_service_starts():
    assert_production_secrets(FakeSettings()) is None


@pytest.mark.parametrize("environment", ["development", "test", "staging"])
def test_non_production_environments_are_left_alone(environment):
    """The defaults exist for these environments; flagging them is noise."""
    settings = FakeSettings(
        environment=environment,
        jwt_secret_key="dev-secret-change-me",
        database_url="postgresql+asyncpg://fooduser:foodpass@postgres-users:5432/users_db",
    )

    assert assert_production_secrets(settings) is None


def test_the_repository_default_jwt_secret_is_refused():
    settings = FakeSettings(jwt_secret_key="dev-secret-change-me")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        assert_production_secrets(settings)


@pytest.mark.parametrize("secret", ["", "changeme", "secret"])
def test_other_well_known_jwt_secrets_are_refused(secret):
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        assert_production_secrets(FakeSettings(jwt_secret_key=secret))


def test_a_short_jwt_secret_is_refused():
    """Not a default, but 16 characters of HMAC key is brute-forceable offline."""
    settings = FakeSettings(jwt_secret_key="abcdef0123456789")

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        assert_production_secrets(settings)


def test_the_compose_database_password_is_refused():
    settings = FakeSettings(
        database_url="postgresql+asyncpg://fooduser:foodpass@postgres-users:5432/users_db"
    )

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        assert_production_secrets(settings)


def test_a_database_name_containing_the_word_is_not_a_finding():
    """The match is against the credentials segment, not the whole URL.

    A guard that fires on a database or host name that merely contains the word
    is a guard someone disables, and then it protects nothing.
    """
    settings = FakeSettings(
        database_url="postgresql+asyncpg://fooduser:Str0ngP4ss@db.internal:5432/foodpass_db"
    )

    assert assert_production_secrets(settings) is None


def test_the_message_names_the_service_and_every_problem_found():
    """One boot, one report — so a misconfigured deploy is fixed in one pass."""
    settings = FakeSettings(
        service_name="orders-service",
        jwt_secret_key="dev-secret-change-me",
        database_url="postgresql+asyncpg://fooduser:foodpass@postgres-orders:5432/orders_db",
    )

    with pytest.raises(RuntimeError) as raised:
        assert_production_secrets(settings)

    message = str(raised.value)
    assert "orders-service" in message
    assert "JWT_SECRET_KEY" in message
    assert "DATABASE_URL" in message


def test_the_message_does_not_echo_the_offending_secret():
    """Startup errors land in logs that are read more widely than the secret store."""
    settings = FakeSettings(
        jwt_secret_key="hunter2-but-far-too-short",
        database_url="postgresql+asyncpg://fooduser:foodpass@postgres-users:5432/users_db",
    )

    with pytest.raises(RuntimeError) as raised:
        assert_production_secrets(settings)

    assert "hunter2-but-far-too-short" not in str(raised.value)

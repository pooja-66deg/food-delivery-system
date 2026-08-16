"""The alembic chain, actually run, and checked against the models it must serve.

Reviewing this service turned up "run ./services/migrate.sh users upgrade head
before enabling the admin flow", on the grounds that ``password_reset_required``
would otherwise be missing in production. The deploy pipeline already does that —
cloudbuild.yaml runs ``alembic upgrade head`` as a per-service Cloud Run job,
with --wait so a failed migration fails the build — so the step was covered.

What was *not* covered is the failure that makes such a step necessary in the
first place: a column added to models.py with no revision to create it. Nothing
catches that. The service's own suite builds its schema with
``Base.metadata.create_all``, so every test sees the model's idea of the table
and none of them ever runs a migration; the mismatch surfaces in production, as
an UndefinedColumn error on a table the code was certain about.

So this runs the real chain against a scratch database and compares the result
with the models. Adding a column without a revision fails here instead of there.

SQLite, not Postgres, because a test suite that needs a live database is a test
suite that does not run. The chain is plain add/drop/alter DDL and applies on
both; a revision that reaches for Postgres-specific syntax will fail this test,
which is the correct moment to notice that it cannot be verified this way.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.models import User

SERVICE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    """A database built the way production builds one: by running the chain."""
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    # alembic.ini's sqlalchemy.url is a placeholder; env.py prefers DATABASE_URL
    # and this makes sure nothing falls back to a real host.
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    cwd = os.getcwd()
    os.chdir(SERVICE_ROOT)
    try:
        command.upgrade(config, "head")
    finally:
        os.chdir(cwd)

    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


def test_the_chain_applies_from_empty_to_head(migrated_db):
    """Every revision in order, on a database that starts with nothing."""
    tables = set(inspect(migrated_db).get_table_names())

    assert "users" in tables
    assert "alembic_version" in tables


def test_password_reset_required_exists_and_is_not_nullable(migrated_db):
    """The column the admin flow depends on, and the shape it depends on.

    Nullable would be worse than absent: ``if user.password_reset_required`` is
    falsey for NULL, so every pre-existing admin would silently skip the forced
    reset rather than failing loudly.
    """
    columns = {c["name"]: c for c in inspect(migrated_db).get_columns("users")}

    assert "password_reset_required" in columns
    assert columns["password_reset_required"]["nullable"] is False


def test_every_model_column_exists_in_the_migrated_schema(migrated_db):
    """The drift check: a model column with no revision behind it.

    This is the failure the "run the migration first" note was really about. The
    suite's own create_all schema can never catch it, because create_all *is* the
    models — only a migrated database disagrees.
    """
    migrated = {c["name"] for c in inspect(migrated_db).get_columns("users")}
    modelled = {c.name for c in User.__table__.columns}
    missing = modelled - migrated

    assert not missing, (
        f"users.{sorted(missing)} exists on the model but no revision creates it. "
        "Add a migration, or production will raise UndefinedColumn on a table the "
        "code is certain about."
    )

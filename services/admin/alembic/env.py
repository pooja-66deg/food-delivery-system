"""Alembic environment for the admin service.

Imports nothing from ``src`` on purpose. A service owns its schema, and a
migration chain that reached back into the monolith's models would recreate the
very coupling the split exists to remove — the two would then have to be
deployed together, which is the opposite of the goal. Each revision spells its
tables out in full, so this chain runs anywhere the service's container runs.

Autogenerate is therefore unavailable here: write revisions by hand.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _url() -> str:
    """This service's own database, from the environment."""
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at the admin service's own "
            "database — never at another service's, and never at the monolith's."
        )
    # Alembic runs on a synchronous driver; the service itself uses asyncpg.
    return url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

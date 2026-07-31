"""Alembic environment — runs migrations with a synchronous engine."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.config import settings
from src.infrastructure.database import Base

# Import every model module so Base.metadata is complete.
import src.modules.users.models  # noqa: F401
import src.modules.restaurants.models  # noqa: F401
import src.modules.orders.models  # noqa: F401
import src.modules.payments.models  # noqa: F401
import src.modules.delivery.models  # noqa: F401
import src.modules.notifications.models  # noqa: F401
import src.modules.events.models  # noqa: F401
import src.modules.reviews.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    # Alembic uses a synchronous driver; strip any async driver qualifier.
    return (
        settings.database_url
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("sqlite+aiosqlite://", "sqlite://")
    )


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

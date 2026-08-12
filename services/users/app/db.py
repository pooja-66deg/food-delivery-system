"""This service's database connection.

One engine, one database — the one named in this service's own settings. There
is deliberately no way to reach another service's data from here: that is what
makes "users is down" a statement about users only.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.database_echo,
    # Bounded on purpose. SQLAlchemy's default is 5 + 10 overflow = 15 per
    # instance, and seven services against one shared Cloud SQL instance is 105
    # against a tier whose max_connections is ~25. That is not theoretical: it
    # exhausted the pool in production, and because the outbox relay needs a
    # connection to publish, the failures were not just a 500 on checkout but
    # domain events that never left the outbox at all.
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    # A connection Cloud SQL has already dropped fails the next statement rather
    # than the checkout, which is how a proxy restart became a request error.
    pool_pre_ping=True,
    pool_recycle=1800,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency: a session per request."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

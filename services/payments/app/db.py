"""This service's database connection.

One engine, one database — the one named in this service's own settings. There
is deliberately no way to reach another service's data from here: that is what
makes "payments is down" a statement about payments only.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.database_echo,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency: a session per request."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

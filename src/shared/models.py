"""Shared SQLAlchemy models and utilities for microservices.

This module provides:
- Base: The SQLAlchemy declarative base for all service models
- AsyncSessionLocal: Factory function for creating async database sessions
- Common column types and utilities for consistency across services
"""
from typing import Optional, AsyncGenerator
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# SQLAlchemy declarative base for all ORM models
Base = declarative_base()


async def get_async_session_factory(database_url: str) -> async_sessionmaker:
    """Create an async session factory for a service's database.

    This factory allows each microservice to have its own isolated database
    while using the same SQLAlchemy patterns and session management.

    Args:
        database_url: The database connection URL (PostgreSQL with asyncpg).

    Returns:
        An async_sessionmaker that can be used to create AsyncSession instances.

    Example:
        session_factory = await get_async_session_factory("postgresql+asyncpg://...")
        async with session_factory() as session:
            result = await session.execute(select(Model))
    """
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(
    session_factory: async_sessionmaker,
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI routes to inject database sessions.

    Each microservice's main.py should create a session factory and use this
    function as a dependency getter in their routers.

    Args:
        session_factory: An async_sessionmaker instance.

    Yields:
        AsyncSession instances for database operations.

    Example:
        app = FastAPI()
        session_factory = async_sessionmaker(engine, class_=AsyncSession)

        @app.get("/orders")
        async def get_orders(session: AsyncSession = Depends(
            lambda: get_db_session(session_factory)
        )):
            ...
    """
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

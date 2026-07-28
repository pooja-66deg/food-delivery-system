"""Shared pytest fixtures.

Tests run against an in-memory SQLite database and an in-memory (fake) Redis so
the red-green loop needs no live infrastructure. A ``StaticPool`` keeps a single
connection alive so the in-memory schema persists across the session.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.database import Base, get_db
from src.infrastructure.redis import get_redis
from src.main import app

# Import model modules so their tables register on Base.metadata.
import src.modules.users.models  # noqa: F401,E402
import src.modules.restaurants.models  # noqa: F401,E402
import src.modules.orders.models  # noqa: F401,E402


@pytest.fixture
def client():
    """Provide a synchronous test client for FastAPI."""
    return TestClient(app)


@pytest_asyncio.fixture
async def api_client():
    """Async HTTP client wired to the app with in-memory DB + fake Redis.

    Uses ASGITransport so the app and DB run on the same event loop; the app's
    real DB/Redis/Kafka dependencies are overridden so no live infra is needed.
    """
    import fakeredis.aioredis

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    async def _override_get_redis():
        return redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    """Provide an isolated in-memory async SQLite session per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def fake_redis():
    """Provide an in-memory async Redis client."""
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()

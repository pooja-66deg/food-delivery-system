"""Shared pytest fixtures.

Tests run against an in-memory SQLite database and an in-memory (fake) Redis so
the red-green loop needs no live infrastructure. A ``StaticPool`` keeps a single
connection alive so the in-memory schema persists across the session.
"""

import os

# Test bootstrap: provide the settings the app requires at import time so a
# fresh clone can run `pytest` with no manual env setup. Real values (or a
# .env) still override these via setdefault.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.adapters.database import Base, get_db
from src.adapters.redis import get_redis
from src.main import app

# Import model modules so their tables register on Base.metadata.
import src.modules.users.models  # noqa: F401,E402
import src.modules.restaurants.models  # noqa: F401,E402
import src.modules.orders.models  # noqa: F401,E402
import src.modules.payments.models  # noqa: F401,E402
import src.modules.delivery.models  # noqa: F401,E402
import src.modules.notifications.models  # noqa: F401,E402
import src.modules.events.models  # noqa: F401,E402
import src.modules.reviews.models  # noqa: F401,E402


@pytest.fixture
def client():
    """Provide a synchronous test client for FastAPI."""
    return TestClient(app)


@pytest_asyncio.fixture
async def _mem_engine():
    """A single in-memory SQLite engine shared within one test (StaticPool keeps
    one connection alive, so all consumers see the same data)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(_mem_engine):
    """Async HTTP client wired to the app with in-memory DB + fake Redis.

    Uses ASGITransport so the app and DB run on the same event loop; the app's
    real DB/Redis/Kafka dependencies are overridden so no live infra is needed.
    """
    import fakeredis.aioredis

    session_factory = async_sessionmaker(_mem_engine, class_=AsyncSession, expire_on_commit=False)
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


@pytest_asyncio.fixture
async def app_session(_mem_engine):
    """A DB session bound to the SAME engine as ``api_client`` in this test, for
    seeding/inspecting data the app also sees (e.g. promoting a user to admin)."""
    factory = async_sessionmaker(_mem_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


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

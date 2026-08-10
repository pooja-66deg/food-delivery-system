"""Fixtures for the users service.

Everything runs against an in-memory SQLite database and a fake Redis, so the
suite needs no infrastructure — which matters more here than it did in the
monolith: a service whose tests need a live stack is a service nobody runs the
tests for.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest_asyncio.fixture
async def engine():
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
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_session(session) -> AsyncSession:
    """Alias for session fixture to support test templates."""
    return session


@pytest_asyncio.fixture
async def client(engine):
    """The service's own app, with its database and Redis swapped for fakes."""
    import fakeredis.aioredis

    from app import redis_client
    from app.db import get_db
    from app.main import app

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _get_db():
        async with factory() as s:
            yield s

    async def _get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[redis_client.get_redis] = _get_redis
    # ASGITransport drives the app directly, so lifespan never runs — no Kafka
    # producer, no consumer thread, no relay. The outbox rows are still written,
    # which is what the tests assert on.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def register_payload():
    def _build(**overrides):
        payload = {
            "email": "cara@example.com",
            "phone": "+919876543210",
            "first_name": "Cara",
            "last_name": "Customer",
            "password": "supersecret1",
            "role": "customer",
        }
        payload.update(overrides)
        return payload

    return _build

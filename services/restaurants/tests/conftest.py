"""Fixtures for the restaurants service.

In-memory SQLite and a fake Redis, so the suite needs no infrastructure — which
matters more here than it did in the monolith: a service whose tests need a live
stack is a service nobody runs the tests for.
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
async def client(engine):
    """The service's own app, with its database swapped for a fake."""
    from app.db import get_db
    from app.main import app

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    # ASGITransport drives the app directly, so lifespan never runs — no Kafka
    # producer, no consumer thread, no relay. Outbox rows are still written,
    # which is what the tests assert on.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def auth():
    """Authorization headers for a caller, signed with this service's own secret.

    A fixture rather than a plain helper: pytest's importlib mode does not put
    conftest on the import path, so tests cannot import from it.
    """
    import jwt

    from app.config import settings

    def _headers(user_id: int = 1, role: str = "customer") -> dict:
        claims = {
            "sub": str(user_id), "role": role, "gen": 0,
            "jti": f"t{user_id}", "type": "access",
        }
        encoded = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        return {"Authorization": f"Bearer {encoded}"}

    return _headers

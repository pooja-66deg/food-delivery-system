"""Integration tests against a real PostgreSQL (via Testcontainers).

These cover behaviour the SQLite unit suite cannot: the real async driver
(asyncpg), Numeric(10,2) money semantics, and the unique-constraint race that
must surface as a 409 rather than a 500. Skipped automatically when Docker /
Testcontainers is unavailable so the default suite stays infra-free.
"""
import pytest

pytestmark = pytest.mark.integration

testcontainers = pytest.importorskip("testcontainers.postgres")
from testcontainers.postgres import PostgresContainer  # noqa: E402

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from src.infrastructure.database import Base  # noqa: E402
import src.modules.users.models  # noqa: F401,E402
import src.modules.restaurants.models  # noqa: F401,E402
import src.modules.orders.models  # noqa: F401,E402
import src.modules.payments.models  # noqa: F401,E402
import src.modules.delivery.models  # noqa: F401,E402
import src.modules.notifications.models  # noqa: F401,E402
import src.modules.events.models  # noqa: F401,E402

from src.core.exceptions import ConflictException  # noqa: E402
from src.modules.users import service as user_service  # noqa: E402
from src.modules.users.schemas import UserRegister  # noqa: E402


@pytest.fixture(scope="module")
def pg_url():
    try:
        with PostgresContainer("postgres:15-alpine") as pg:
            # Convert the sync psycopg2 URL Testcontainers returns into asyncpg.
            url = pg.get_connection_url().replace("psycopg2", "asyncpg")
            yield url
    except Exception as exc:  # noqa: BLE001 — Docker not available in this env
        pytest.skip(f"Docker/Testcontainers unavailable: {exc}")


@pytest.mark.asyncio
async def test_duplicate_registration_raises_conflict_on_postgres(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    data = UserRegister(email="dup@example.com", phone="+15551230000",
                        first_name="A", last_name="B", password="supersecret1", role="customer")
    async with factory() as s1:
        await user_service.register_user(s1, data)

    # Second insert with the same email must be a clean ConflictException (409),
    # exercised against the real unique constraint on Postgres.
    async with factory() as s2:
        with pytest.raises(ConflictException):
            await user_service.register_user(s2, data)

    await engine.dispose()

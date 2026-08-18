"""What the readiness probe tells the load balancer when the database is gone.

The distinction this pins is not cosmetic. Cloud Run and Kubernetes route on the
status code and never look at the body, so answering 200 with ``"degraded"``
inside it told them the instance was ready while every request it received
failed. Traffic kept arriving because the platform had been told, in the only
language it reads, that everything was fine.

``/health`` must *not* follow suit: it answers "is this process alive", and a
database blip that fails liveness gets the container killed and restarted, which
turns a dependency outage into an outage of its own.
"""

import pytest

from app import main


class _DeadEngine:
    """An engine whose every connection attempt fails, like a database that is down."""

    def connect(self):
        raise OSError("connection refused")


@pytest.mark.asyncio
async def test_ready_is_200_when_the_database_answers(client, engine, monkeypatch):
    # The probe reads the module-level engine directly rather than going through
    # the get_db dependency the client fixture overrides, so pointing it at the
    # suite's in-memory database is what makes this the happy path and not
    # another unreachable-database case.
    monkeypatch.setattr(main, "engine", engine)

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_ready_is_503_when_the_database_is_unreachable(client, monkeypatch):
    monkeypatch.setattr(main, "engine", _DeadEngine())

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}


@pytest.mark.asyncio
async def test_health_stays_200_when_the_database_is_unreachable(client, monkeypatch):
    """Liveness is about the process, and this process is alive.

    If this went unhealthy with the database, the orchestrator would restart a
    container that has nothing wrong with it — repeatedly, for as long as the
    outage lasts.
    """
    monkeypatch.setattr(main, "engine", _DeadEngine())

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

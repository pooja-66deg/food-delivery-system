"""The admin service's proxy for creating the platform's first administrator.

``POST /admin/bootstrap`` sits outside the admin-role dependency every other
route here carries, because there is no administrator to authenticate as yet.
That is unavoidable, and it is also why the route needs a secret: the gateway
proxies ``/api/admin/`` straight to this service, so without one the first
stranger to call it on a fresh deployment becomes its administrator.

The comparison itself belongs upstream, in the service that creates the account —
a secret that has to match in two places to work, and either place to be wrong to
fail, is a secret with two chances to be misconfigured. So these tests pin what
this service is actually responsible for: refusing calls it knows cannot succeed,
forwarding the header when they might, and passing upstream's refusal through
unchanged instead of dressing it up as its own failure.
"""

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_bootstrap_refuses_when_no_secret_is_configured(client, monkeypatch):
    """Fail closed, matching upstream — a half-configured deployment leaves no door open."""
    monkeypatch.setattr(settings, "bootstrap_secret", None)

    response = await client.post(
        "/admin/bootstrap",
        json={"email": "attacker@evil.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "anything"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_refuses_a_missing_header(client, monkeypatch):
    """Refused here without calling upstream at all: it cannot possibly succeed."""
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    response = await client.post(
        "/admin/bootstrap",
        json={"email": "attacker@evil.com", "password": "TempPassword123"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_forwards_the_secret_upstream(client, monkeypatch):
    """The caller's header reaches the users service as X-Bootstrap-Secret.

    Checking the value here as well would be the second of two places to get it
    right; forwarding it is this service's whole job.
    """
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")
    seen = {}

    class _Response:
        status_code = 201

        @staticmethod
        def json():
            return {
                "id": 1,
                "email": "admin@test.com",
                "first_name": "Admin",
                "last_name": "User",
                "role": "admin",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00",
            }

    class _Users:
        async def post(self, path, **kwargs):
            seen["path"] = path
            seen["headers"] = kwargs.get("headers")
            return _Response()

        @staticmethod
        def unwrap(response, expect=200):
            return response.json()

    monkeypatch.setattr("app.router.users", lambda: _Users())

    response = await client.post(
        "/admin/bootstrap",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "bootstrap-me"},
    )

    assert response.status_code == 201
    assert seen["path"] == "/auth/internal/bootstrap-admin"
    assert seen["headers"] == {"X-Bootstrap-Secret": "bootstrap-me"}


@pytest.mark.asyncio
async def test_upstream_rejection_is_passed_through_as_401(client, monkeypatch):
    """Upstream is the authority on the secret, so its "no" stays a "no".

    Left to the generic path, a 401 from the users service becomes a 503 — this
    service reporting the dependency as unavailable when it answered perfectly
    well, which sends whoever is debugging it to look for an outage that is not
    happening.
    """
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    class _Response:
        status_code = 401

        @staticmethod
        def json():
            return {"detail": "Invalid or missing bootstrap secret"}

    class _Users:
        async def post(self, path, **kwargs):
            return _Response()

        @staticmethod
        def unwrap(response, expect=200):
            raise AssertionError("must not unwrap a rejected call")

    monkeypatch.setattr("app.router.users", lambda: _Users())

    response = await client.post(
        "/admin/bootstrap",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "wrong-but-present"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_second_bootstrap_is_a_conflict_not_a_500(client, monkeypatch):
    """Once an admin exists the route is closed, however good the secret is."""
    monkeypatch.setattr(settings, "bootstrap_secret", "bootstrap-me")

    class _Response:
        status_code = 409

        @staticmethod
        def json():
            return {"detail": "Admin account already exists"}

    class _Users:
        async def post(self, path, **kwargs):
            return _Response()

        @staticmethod
        def unwrap(response, expect=200):
            raise AssertionError("must not unwrap a conflict")

    monkeypatch.setattr("app.router.users", lambda: _Users())

    response = await client.post(
        "/admin/bootstrap",
        json={"email": "admin@test.com", "password": "TempPassword123"},
        headers={"X-Bootstrap-Secret": "bootstrap-me"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

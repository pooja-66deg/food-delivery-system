"""Driver-level failures, answered rather than raised.

Every one of these was an unhandled 500 in production. ``install_error_handlers``
registered a handler for ``AppException`` only, so a DBAPIError went straight to
Starlette's ServerErrorMiddleware — 98 of them in one 90-minute window, across
six services, reachable unauthenticated on two routes.

The bounded types in shared/ids.py are the real fix; this is the net underneath,
and it has to distinguish "the caller sent something impossible" from "the
database is down", because those are a 4xx and a 5xx respectively.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError

from shared.errors import install_error_handlers


class _Location(BaseModel):
    """delivery's LocationBody, field for field."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


def _client(exc: Exception) -> TestClient:
    """An app whose one route raises ``exc``."""
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise exc

    # A JSON body bounded exactly as delivery's LocationBody is. Both halves
    # matter: the bounds make Pydantic reject inf, and a *body* is what puts a
    # real float in `input` — a query param keeps the raw string "1e400", which
    # serialises fine, so only the body path ever crashed.
    @app.post("/echo")
    async def echo(body: _Location):
        return {"latitude": body.latitude}

    return TestClient(app, raise_server_exceptions=False)


def _dbapi(orig: Exception) -> DBAPIError:
    """A DBAPIError wrapping ``orig``, the shape SQLAlchemy actually raises.

    Registered on DBAPIError rather than a subclass on purpose: asyncpg's errors
    are not all mapped to one, and the production tracebacks read
    ``sqlalchemy.exc.DBAPIError``. A handler on ``DataError`` never fired.
    """
    return DBAPIError("SELECT 1", {}, orig)


class _Named(Exception):
    """An exception standing in for an asyncpg one, matched on class name."""


def _as(name: str) -> Exception:
    return type(name, (_Named,), {})("boom")


class TestOutOfRangeIsAClientError:
    def test_int32_overflow_is_422_not_500(self):
        r = _client(_dbapi(_as("DataError"))).get("/boom")
        assert r.status_code == 422
        assert "not valid" in r.json()["detail"]

    @pytest.mark.parametrize("name", [
        "InvalidRowCountInLimitClauseError",
        "InvalidRowCountInResultOffsetClauseError",
        "NumericValueOutOfRangeError",
        "InvalidTextRepresentationError",
    ])
    def test_bad_pagination_and_casts_are_422(self, name):
        assert _client(_dbapi(_as(name))).get("/boom").status_code == 422

    def test_overflowerror_from_the_encoder_is_422(self):
        # asyncpg's int4 encoder raises this directly while binding.
        assert _client(_dbapi(OverflowError("out of int32 range"))).get("/boom").status_code == 422


class TestConstraintViolations:
    def test_null_in_a_not_null_column_is_422(self):
        # PATCH /notifications/preferences {"sms_enabled": null} was a 500.
        assert _client(_dbapi(_as("NotNullViolationError"))).get("/boom").status_code == 422

    def test_duplicate_key_is_409(self):
        r = _client(_dbapi(_as("UniqueViolationError"))).get("/boom")
        assert r.status_code == 409


class TestDatabaseUnavailableIsRetryable:
    @pytest.mark.parametrize("orig", [
        _as("TooManyConnectionsError"),
        _as("ConnectionDoesNotExistError"),
        ConnectionRefusedError(111, "Connection refused"),
    ])
    def test_connection_failures_are_503(self, orig):
        """503, not 500. Pool exhaustion surfaced as an unhandled 500 out of
        checkout, which tells a client the request was wrong; it was not, and it
        is worth retrying."""
        r = _client(_dbapi(orig)).get("/boom")
        assert r.status_code == 503
        assert "retry" in r.json()["detail"].lower()


class TestGenuineFaultsStayFaults:
    def test_an_unrecognised_driver_error_is_not_dressed_up_as_a_client_error(self):
        """A server fault must keep its 500 rather than be mislabelled 4xx."""
        r = _client(_dbapi(_as("InternalServerError"))).get("/boom")
        assert r.status_code == 500


class TestNonFiniteFloatsSerialise:
    def test_infinity_in_a_validation_error_is_422_not_500(self):
        """The 422 body echoes the offending input, and Starlette renders JSON
        with allow_nan=False — so FastAPI's own handler was the thing that
        crashed. POST /delivery/location with 1e400 returned a text/plain 500."""
        r = _client(ValueError("unused")).post(
            "/echo", content='{"latitude": 1e400, "longitude": 0}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/json")
        assert "Infinity" in r.text

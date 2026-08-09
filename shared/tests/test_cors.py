"""Every service has to answer a preflight, not just the one that mints tokens.

The bug this guards against shipped and reached production: only the users
service installed the middleware, on the reasoning that the others sit behind the
gateway and the browser never opens a connection to them. True, and it does not
follow — nginx forwards a response untouched, so the browser checks each
service's own headers against the SPA's origin. Sign-in worked and every other
call in the app failed its preflight with a 405, because FastAPI has no OPTIONS
route and nothing was there to intercept one.

These tests are deliberately about the *contract* rather than any one service,
which is why they live beside shared/cors.py: a new service added later without
install_cors is the same outage again, and the assertion that catches it cannot
sit in a suite that new service does not have.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.cors import install_cors, split_origins

ORIGIN = "https://food-frontend-660060329211.us-central1.run.app"
OTHER = "https://food-frontend-orhxitfkxa-uc.a.run.app"


def _app(origins: list[str]) -> TestClient:
    app = FastAPI()
    install_cors(app, origins)

    @app.get("/thing")
    async def thing():
        return {"ok": True}

    return TestClient(app)


def test_preflight_is_answered():
    """The exact request the browser sends before a credentialed GET. Without
    the middleware this is a 405 and the real call never happens."""
    client = _app([ORIGIN])
    r = client.options(
        "/thing",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_the_actual_response_carries_the_header_too():
    """A passing preflight is not enough — the browser checks the real response
    as well, and a missing header there fails just as hard."""
    client = _app([ORIGIN])
    r = client.get("/thing", headers={"Origin": ORIGIN})
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_credentials_are_allowed():
    """The SPA sends an Authorization header. Without this the browser discards
    the response even though the request succeeded."""
    client = _app([ORIGIN])
    r = client.get("/thing", headers={"Origin": ORIGIN})
    assert r.headers["access-control-allow-credentials"] == "true"


def test_both_cloud_run_hostnames_are_matched():
    """Cloud Run serves the frontend on two hostnames and Origin matching is
    byte-exact, so listing one locks out everyone who arrived by the other."""
    client = _app([ORIGIN, OTHER])
    for origin in (ORIGIN, OTHER):
        r = client.get("/thing", headers={"Origin": origin})
        assert r.headers["access-control-allow-origin"] == origin


def test_an_unlisted_origin_gets_nothing():
    """The list is a list, not decoration."""
    client = _app([ORIGIN])
    r = client.get("/thing", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://a.example", ["https://a.example"]),
        ("https://a.example,https://b.example", ["https://a.example", "https://b.example"]),
        # Whitespace around a comma is what a human editing a deploy variable
        # actually types, and an origin with a leading space matches nothing.
        (" https://a.example , https://b.example ", ["https://a.example", "https://b.example"]),
        ("", []),
        (",,", []),
    ],
)
def test_origin_parsing(raw, expected):
    assert split_origins(raw) == expected

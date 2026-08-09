"""This service answers a CORS preflight.

One assertion, in every service, because the failure it catches is invisible
until a browser tries: FastAPI has no OPTIONS route of its own, so a service
without the middleware answers 405 and the SPA's real request never leaves the
browser. That is precisely what shipped — only users installed it, and every
other call in the app was blocked in production while the services themselves
looked perfectly healthy in every log and every curl.

curl does not send an Origin header, so nothing short of this notices.

The origin is the configured default rather than a production hostname, and is
deliberately not monkeypatched: install_cors runs at import time, so the list is
already baked into the middleware by the time a test could patch the setting.
What is under test is that the middleware is installed and honours its
configuration — which origins production configures is the deploy's business.
"""

ORIGIN = "http://localhost:5173"


async def test_preflight_is_answered(client):
    r = await client.options(
        "/health",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    # 405 here means the middleware is missing, not that the route is.
    assert r.status_code != 405, "no CORS middleware — see shared/cors.py"
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.headers.get("access-control-allow-credentials") == "true"


async def test_a_normal_response_carries_the_header(client):
    """A passing preflight is not enough — the browser checks the real response
    as well, and a missing header there fails just as hard."""
    r = await client.get("/health", headers={"Origin": ORIGIN})
    assert r.headers.get("access-control-allow-origin") == ORIGIN

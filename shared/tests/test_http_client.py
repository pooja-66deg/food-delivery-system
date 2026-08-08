"""The circuit breaker and the timeout — the two things that make a sync call
between services survivable.

Everything here is about what happens when the *other* service misbehaves, since
that is the only reason this module exists.
"""
import httpx
import pytest

from src.shared.errors import ServiceUnavailableException
from src.shared.http_client import CircuitBreaker, ServiceClient


def test_breaker_stays_closed_below_the_threshold():
    breaker = CircuitBreaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert not breaker.is_open


def test_breaker_opens_on_consecutive_failures():
    breaker = CircuitBreaker(threshold=3)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.is_open


def test_a_success_resets_the_count():
    """Consecutive, not cumulative: a healthy service must not accumulate its way
    to an open circuit over days of ordinary traffic."""
    breaker = CircuitBreaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert not breaker.is_open


def test_breaker_half_opens_after_the_cooldown(monkeypatch):
    """After the cooldown one call goes through, or the circuit never recovers."""
    breaker = CircuitBreaker(threshold=1, cooldown_seconds=10)
    clock = [1000.0]
    monkeypatch.setattr("src.shared.http_client.time.monotonic", lambda: clock[0])

    breaker.record_failure()
    assert breaker.is_open

    clock[0] += 11
    assert not breaker.is_open, "cooldown elapsed but the circuit never let a probe through"


async def test_timeout_becomes_service_unavailable():
    """A hang must surface as 503 — retryable — not as a 500 or a stuck request."""
    def _hang(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow", request=request)

    client = ServiceClient("http://restaurants", name="restaurants")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_hang), base_url="http://restaurants"
    )

    with pytest.raises(ServiceUnavailableException):
        await client.get("/anything")
    await client.aclose()


async def test_repeated_timeouts_open_the_circuit():
    """Once open, calls fail immediately instead of burning a timeout each."""
    calls = []

    def _hang(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        raise httpx.TimeoutException("too slow", request=request)

    client = ServiceClient(
        "http://restaurants", name="restaurants", breaker=CircuitBreaker(threshold=2)
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_hang), base_url="http://restaurants"
    )

    for _ in range(2):
        with pytest.raises(ServiceUnavailableException):
            await client.get("/anything")
    assert len(calls) == 2

    with pytest.raises(ServiceUnavailableException):
        await client.get("/anything")
    assert len(calls) == 2, "circuit was open but the call still went out"
    await client.aclose()


async def test_a_4xx_is_an_answer_not_a_failure():
    """A run of legitimate rejections must not trip the circuit on a healthy
    service — that would turn "your cart is invalid" into "checkout is down"."""
    def _rejects(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no such restaurant"})

    client = ServiceClient(
        "http://restaurants", name="restaurants", breaker=CircuitBreaker(threshold=2)
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_rejects), base_url="http://restaurants"
    )

    for _ in range(5):
        response = await client.get("/anything")
        assert response.status_code == 404
    assert not client._breaker.is_open
    await client.aclose()


async def test_a_5xx_does_count_as_a_failure():
    def _breaks(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = ServiceClient(
        "http://restaurants", name="restaurants", breaker=CircuitBreaker(threshold=2)
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_breaks), base_url="http://restaurants"
    )

    for _ in range(2):
        with pytest.raises(ServiceUnavailableException):
            await client.get("/anything")
    assert client._breaker.is_open
    await client.aclose()


async def test_the_callers_token_is_forwarded():
    """Services forward the end user's token rather than holding a machine
    credential, so the called service applies the same rules to the same person."""
    seen = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    client = ServiceClient("http://restaurants", name="restaurants")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_capture), base_url="http://restaurants"
    )

    await client.post("/x", json={}, auth_header="Bearer abc123")
    assert seen["auth"] == "Bearer abc123"
    await client.aclose()

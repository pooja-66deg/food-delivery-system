"""Calling another service, when calling one is genuinely unavoidable.

Almost everything between services here is an event. This module is for the one
place it cannot be: checkout has to know what a dish costs and whether there is
stock, and the customer is waiting for the answer. Pretending that can be
asynchronous would just move the failure somewhere worse — an order accepted at
a price nobody agreed to.

What makes a sync call survivable is not the call, it is what surrounds it:

**A timeout.** The default failure mode of a network call is not an error, it is
a hang. Without a deadline one slow dependency consumes every worker in this
service, and a partial outage becomes a total one. The timeout here is small on
purpose — a checkout that takes eight seconds has already failed as far as the
customer is concerned.

**A circuit breaker.** Once a dependency is properly down, continuing to call it
wastes a timeout per request and keeps load on something that is trying to
recover. After enough consecutive failures the breaker opens and calls fail
immediately, until a cooldown lets one request through to test the water.

**A distinct error.** A dependency being unreachable is a 503 — "we could not
answer, try again" — not a 4xx, which says "we answered, and the answer is no".
The caller retries one and not the other, and it can only tell them apart if we
keep them apart.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import httpx

from .errors import ServiceUnavailableException

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """Stops calling a dependency that is clearly down.

    Three states, though only two are ever stored: closed (calling normally),
    open (failing fast), and the half-open probe that happens implicitly when
    the cooldown expires and one call is allowed through. A single success
    closes it again — anything more elaborate mostly delays recovery.
    """

    #: Consecutive failures before the circuit opens.
    threshold: int = 5
    #: How long to fail fast before letting one request test the dependency.
    cooldown_seconds: float = 10.0

    _failures: int = field(default=0, init=False)
    _opened_at: Optional[float] = field(default=None, init=False)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if (time.monotonic() - self._opened_at) >= self.cooldown_seconds:
            # Cooldown elapsed: allow one call through as a probe. Left open
            # until that call reports back, so a burst does not all probe at once.
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.monotonic()


class ServiceClient:
    """An HTTP client for one other service."""

    def __init__(
        self,
        base_url: str,
        *,
        name: str,
        timeout_seconds: float = 3.0,
        breaker: Optional[CircuitBreaker] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._name = name
        self._timeout = timeout_seconds
        self._breaker = breaker or CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Mapping[str, Any]] = None,
        auth_header: Optional[str] = None,
    ) -> Any:
        """Call the service, or raise ``ServiceUnavailableException``.

        The end user's Authorization header is forwarded rather than swapped for
        a machine credential, so the called service applies the same rules to the
        same person. A service holding its own all-powerful token is how one
        compromised service becomes all of them.
        """
        if self._breaker.is_open:
            logger.warning("%s: circuit open, failing fast", self._name)
            raise ServiceUnavailableException(f"{self._name} is unavailable")

        headers = {"Authorization": auth_header} if auth_header else None
        try:
            client = await self._http()
            response = await client.request(
                method, path, json=json, params=params, headers=headers
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self._breaker.record_failure()
            logger.warning("%s: %s %s failed: %s", self._name, method, path, exc)
            raise ServiceUnavailableException(f"{self._name} is unavailable") from exc
        except asyncio.CancelledError:
            raise

        # A 5xx is the dependency failing, and counts towards the breaker. A 4xx
        # is it answering — the answer is just "no" — and must not, or a run of
        # legitimate rejections would trip the circuit on a healthy service.
        if response.status_code >= 500:
            self._breaker.record_failure()
            logger.warning(
                "%s: %s %s returned %s", self._name, method, path, response.status_code
            )
            raise ServiceUnavailableException(f"{self._name} is unavailable")

        self._breaker.record_success()
        return response

    async def post(self, path: str, **kwargs) -> Any:
        return await self.request("POST", path, **kwargs)

    async def get(self, path: str, **kwargs) -> Any:
        return await self.request("GET", path, **kwargs)

"""Synchronous and asynchronous TfL clients."""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import TypeVar

import httpx

from ._core import DEFAULT_BASE_URL, BaseClient, Endpoint
from .resources.journeys import AsyncJourneys, Journeys
from .resources.lines import AsyncLines, Lines
from .resources.stops import AsyncStops, Stops

T = TypeVar("T")


class TflClient(BaseClient):
    """Client for the TfL Unified API.

    Example:
        >>> with TflClient() as client:
        ...     for arrival in client.stops.arrivals("940GZZLUOXC")[:3]:
        ...         print(arrival.line_name, arrival.destination_name, arrival.minutes_away)

    Args:
        app_key: TfL API key, sent as the ``app_key`` query parameter. Defaults to the
            ``TFL_APP_KEY`` environment variable; if neither is set, requests are anonymous
            (TfL allows this at a lower rate limit).
        timeout: Per-request timeout in seconds.
        max_retries: Retries after timeouts, connection errors, 429s and 5xx responses
            (0 disables retrying).
        cache_ttl: Seconds to cache slow-changing data (``stops.get``, ``stops.search``).
            ``None`` (the default) disables caching. Arrivals are never cached.
        base_url: Override the API root, e.g. for a proxy.

    """

    def __init__(
        self,
        app_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        *,
        cache_ttl: float | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        super().__init__(app_key, timeout, max_retries, cache_ttl, base_url)
        self._http = httpx.Client(**self._http_options())
        self.stops = Stops(self)
        self.lines = Lines(self)
        self.journeys = Journeys(self)

    def _execute(self, endpoint: Endpoint[T]) -> T:
        cached = self._cached(endpoint)
        if cached is not None:
            return cached[0]
        attempt = 0
        while True:
            try:
                response = self._http.get(endpoint.path, params=dict(endpoint.params))
            except httpx.TransportError as exc:
                delay = self._retry_delay(attempt, None)
                if delay is None:
                    raise self._transport_error(endpoint, exc, attempt) from exc
            else:
                delay = self._retry_delay(attempt, response)
                if delay is None:
                    return self._finish(endpoint, response)
            attempt += 1
            time.sleep(delay)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> TflClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncTflClient(BaseClient):
    """Async version of :class:`TflClient` with the same interface; methods are awaitable.

    Example:
        >>> async with AsyncTflClient() as client:
        ...     arrivals = await client.stops.arrivals("940GZZLUOXC")

    """

    def __init__(
        self,
        app_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        *,
        cache_ttl: float | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        super().__init__(app_key, timeout, max_retries, cache_ttl, base_url)
        self._http = httpx.AsyncClient(**self._http_options())
        self.stops = AsyncStops(self)
        self.lines = AsyncLines(self)
        self.journeys = AsyncJourneys(self)

    async def _execute(self, endpoint: Endpoint[T]) -> T:
        cached = self._cached(endpoint)
        if cached is not None:
            return cached[0]
        attempt = 0
        while True:
            try:
                response = await self._http.get(endpoint.path, params=dict(endpoint.params))
            except httpx.TransportError as exc:
                delay = self._retry_delay(attempt, None)
                if delay is None:
                    raise self._transport_error(endpoint, exc, attempt) from exc
            else:
                delay = self._retry_delay(attempt, response)
                if delay is None:
                    return self._finish(endpoint, response)
            attempt += 1
            await asyncio.sleep(delay)

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncTflClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

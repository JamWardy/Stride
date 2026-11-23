"""I/O-free building blocks shared by the sync and async clients.

Each SDK method is described as an :class:`Endpoint` (path, query params, how to parse the
JSON, whether it may be cached). The sync and async clients only differ in how they send
the HTTP request and how they sleep between retries; everything else lives here.
"""

from __future__ import annotations

import email.utils
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Generic, TypeVar

import httpx

from .errors import (
    TflAuthError,
    TflError,
    TflNotFoundError,
    TflRateLimitError,
    TflServerError,
)

T = TypeVar("T")

DEFAULT_BASE_URL = "https://api.tfl.gov.uk"
APP_KEY_ENV_VAR = "TFL_APP_KEY"
try:
    __version__ = version("tfl-sdk")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"
USER_AGENT = f"tfl-sdk/{__version__} (unofficial)"

ParamValue = str | int | float


@dataclass(frozen=True)
class Endpoint(Generic[T]):
    """A single API call: where to send it and how to turn the JSON into models.

    ``parse_error`` lets an endpoint turn a non-2xx response into its own error type (e.g.
    the journey planner's 300); returning ``None`` falls back to the standard mapping.
    """

    path: str
    parse: Callable[[Any], T]
    params: Mapping[str, ParamValue] = field(default_factory=dict)
    cacheable: bool = False
    parse_error: Callable[[httpx.Response], TflError | None] | None = None


def json_list(raw: Any, key: str) -> Any:
    """Return the list under ``key`` in a JSON object (``[]`` if missing or null).

    Raises ``ValueError`` if ``raw`` is not an object, so a response of the wrong shape
    surfaces as a :class:`TflError` rather than an ``AttributeError``.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object with {key!r}, got {type(raw).__name__}")
    return raw.get(key) or []


# --------------------------------------------------------------------------- retries


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter.

    The delay before retry ``n`` (0-based) is drawn from
    ``[cap / 2, cap]`` where ``cap = min(max_delay, base_delay * 2**n)``.
    A ``Retry-After`` header, when present, is used instead; if it asks for longer than
    ``max_delay`` the call is not retried, so a large value can't stall the caller.
    """

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0

    def backoff(self, attempt: int) -> float:
        """Return the jittered delay in seconds before retry number ``attempt`` (0-based)."""
        cap = min(self.max_delay, self.base_delay * (2**attempt))
        return float(cap / 2 + random.uniform(0, cap / 2))


def is_retryable_status(status_code: int) -> bool:
    """Return True for responses worth retrying: 429 and any 5xx."""
    return status_code == 429 or status_code >= 500


def parse_retry_after(value: str | None, *, now: float | None = None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) into seconds."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    current = now if now is not None else time.time()
    return max(0.0, when.timestamp() - current)


# --------------------------------------------------------------------------- errors


def _decode_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None


def _redacted_url(response: httpx.Response) -> str:
    return str(response.request.url.copy_remove_param("app_key"))


def error_details(response: httpx.Response) -> dict[str, Any]:
    """Return the ``status_code``, decoded ``body`` and redacted ``url`` for a TflError."""
    return {
        "status_code": response.status_code,
        "body": _decode_body(response),
        "url": _redacted_url(response),
    }


def error_from_response(response: httpx.Response) -> TflError:
    """Map a non-2xx response to the matching :class:`TflError` subclass."""
    kwargs = error_details(response)
    body = kwargs["body"]
    status = response.status_code
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, str) or not message:
        message = response.reason_phrase or "TfL API error"

    if status in (401, 403):
        return TflAuthError(message, **kwargs)
    if status == 404:
        return TflNotFoundError(message, **kwargs)
    if status == 429:
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        return TflRateLimitError(message, retry_after=retry_after, **kwargs)
    if status >= 500:
        return TflServerError(message, **kwargs)
    return TflError(message, **kwargs)


# --------------------------------------------------------------------------- cache


class TTLCache:
    """A minimal in-memory cache whose entries expire ``ttl`` seconds after being stored."""

    def __init__(self, ttl: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self.ttl = ttl
        self._clock = clock
        self._entries: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> tuple[bool, Any]:
        """Return ``(True, value)`` on a fresh hit, otherwise ``(False, None)``."""
        entry = self._entries.get(key)
        if entry is None:
            return False, None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return False, None
        return True, value

    def set(self, key: Any, value: Any) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds, dropping any expired entries."""
        now = self._clock()
        expired = [k for k, (expires_at, _) in self._entries.items() if now >= expires_at]
        for k in expired:
            del self._entries[k]
        self._entries[key] = (now + self.ttl, value)

    def clear(self) -> None:
        """Remove every entry."""
        self._entries.clear()


# --------------------------------------------------------------------------- shared client


class BaseClient:
    """State and logic shared by :class:`TflClient` and :class:`AsyncTflClient`."""

    def __init__(
        self,
        app_key: str | None,
        timeout: float,
        max_retries: int,
        cache_ttl: float | None,
        base_url: str,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        # Read once to build the HTTP client, so kept private: changing them later would
        # have no effect.
        self._app_key = app_key if app_key is not None else os.environ.get(APP_KEY_ENV_VAR)
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self.retry_policy = RetryPolicy(max_retries=max_retries)
        self.cache = TTLCache(cache_ttl) if cache_ttl else None

    def _http_options(self) -> dict[str, Any]:
        params = {"app_key": self._app_key} if self._app_key else {}
        return {
            "base_url": self._base_url,
            "timeout": self._timeout,
            "params": params,
            "headers": {"User-Agent": USER_AGENT, "Accept": "application/json"},
        }

    @staticmethod
    def _cache_key(endpoint: Endpoint[Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return endpoint.path, tuple(sorted((k, str(v)) for k, v in endpoint.params.items()))

    def _cached(self, endpoint: Endpoint[T]) -> tuple[T] | None:
        """Return ``(result,)`` on a cache hit, ``None`` on a miss or when caching is off."""
        if self.cache is None or not endpoint.cacheable:
            return None
        hit, raw = self.cache.get(self._cache_key(endpoint))
        return (endpoint.parse(raw),) if hit else None

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float | None:
        """Seconds to wait before retrying, or ``None`` if the call should not be retried.

        ``response`` is ``None`` when no response was received (timeout or connection error).
        """
        if attempt >= self.retry_policy.max_retries:
            return None
        if response is None:
            return self.retry_policy.backoff(attempt)
        if not is_retryable_status(response.status_code):
            return None
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is None:
            return self.retry_policy.backoff(attempt)
        return retry_after if retry_after <= self.retry_policy.max_delay else None

    def _finish(self, endpoint: Endpoint[T], response: httpx.Response) -> T:
        """Turn a final response into parsed models or raise the matching error."""
        if not response.is_success:
            custom = endpoint.parse_error(response) if endpoint.parse_error else None
            raise custom or error_from_response(response)
        try:
            raw = response.json()
        except ValueError as exc:
            raise TflError(
                "TfL returned a response that is not valid JSON",
                status_code=response.status_code,
                body=response.text or None,
                url=_redacted_url(response),
            ) from exc
        try:
            result = endpoint.parse(raw)
        except ValueError as exc:  # includes pydantic.ValidationError
            raise TflError(
                f"TfL returned a response this SDK could not parse: {exc}",
                status_code=response.status_code,
                body=raw,
                url=_redacted_url(response),
            ) from exc
        if self.cache is not None and endpoint.cacheable:
            self.cache.set(self._cache_key(endpoint), raw)
        return result

    @staticmethod
    def _transport_error(
        endpoint: Endpoint[Any], exc: httpx.TransportError, retries: int
    ) -> TflError:
        """Wrap a timeout or connection failure that has used up its retries."""
        what = "timed out" if isinstance(exc, httpx.TimeoutException) else "failed"
        suffix = f" after {retries} retries" if retries else ""
        return TflError(f"Request to {endpoint.path} {what}{suffix}: {exc}")

"""Exceptions raised by the TfL SDK."""

from __future__ import annotations

from typing import Any


class TflError(Exception):
    """Base class for every error raised by this SDK.

    Attributes:
        status_code: HTTP status code, or ``None`` if no response was received (e.g. timeout).
        body: Decoded JSON response body if possible, otherwise the raw text (or ``None``).
        url: The URL that was requested, with the app key removed.

    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body
        self.url = url

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"[{self.status_code}] {self.message}"


class TflAuthError(TflError):
    """The app key was missing, invalid or not allowed to call this endpoint (401/403)."""


class TflNotFoundError(TflError):
    """The requested resource does not exist (404)."""


class TflRateLimitError(TflError):
    """Too many requests (429). ``retry_after`` holds the server's hint in seconds, if any."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        url: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body, url=url)
        self.retry_after = retry_after


class TflServerError(TflError):
    """TfL returned a 5xx error."""

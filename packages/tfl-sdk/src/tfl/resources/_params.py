"""Helpers for building request paths and query parameters."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import quote


def segment(value: str) -> str:
    """Percent-encode a value used as a single URL path segment."""
    return quote(value, safe="")


def csv(values: str | Sequence[str]) -> str:
    """Join values with commas; a single string is treated as one value, not as characters."""
    return values if isinstance(values, str) else ",".join(values)

"""``client.lines``: line status and disruptions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from .._core import Endpoint
from ..models.lines import Disruption, LineStatus
from ._params import csv, segment

if TYPE_CHECKING:
    from ..client import AsyncTflClient, TflClient

_line_statuses = TypeAdapter(list[LineStatus])
_disruptions = TypeAdapter(list[Disruption])


# --------------------------------------------------------------------------- endpoint specs


def _status_endpoint(modes: str | Sequence[str]) -> Endpoint[list[LineStatus]]:
    if not modes:
        raise ValueError("modes must name at least one mode, e.g. 'tube'")
    return Endpoint(f"/Line/Mode/{segment(csv(modes))}/Status", _line_statuses.validate_python)


def _disruptions_endpoint(line_id: str) -> Endpoint[list[Disruption]]:
    return Endpoint(f"/Line/{segment(line_id)}/Disruption", _disruptions.validate_python)


# --------------------------------------------------------------------------- resources


class Lines:
    """Line endpoints for :class:`~tfl.TflClient`."""

    def __init__(self, client: TflClient) -> None:
        self._client = client

    def status(self, modes: str | Sequence[str] = ("tube",)) -> list[LineStatus]:
        """Fetch the current status of every line on the given modes. Never cached.

        Args:
            modes: One mode or several, e.g. ``"tube"`` or ``("tube", "dlr")``.

        Returns:
            One entry per line, each with its current ``statuses`` (usually one).

        Raises:
            ValueError: If ``modes`` is empty.

        """
        return self._client._execute(_status_endpoint(modes))

    def disruptions(self, line_id: str) -> list[Disruption]:
        """Fetch current disruptions on a line. Never cached.

        Args:
            line_id: A line id such as ``"central"``.

        Returns:
            The disruptions; empty when the line has none.

        """
        return self._client._execute(_disruptions_endpoint(line_id))


class AsyncLines:
    """Line endpoints for :class:`~tfl.AsyncTflClient`. See :class:`Lines`."""

    def __init__(self, client: AsyncTflClient) -> None:
        self._client = client

    async def status(self, modes: str | Sequence[str] = ("tube",)) -> list[LineStatus]:
        """Fetch the current status of every line on the given modes. See :meth:`Lines.status`."""
        return await self._client._execute(_status_endpoint(modes))

    async def disruptions(self, line_id: str) -> list[Disruption]:
        """Fetch current disruptions on a line. See :meth:`Lines.disruptions`."""
        return await self._client._execute(_disruptions_endpoint(line_id))

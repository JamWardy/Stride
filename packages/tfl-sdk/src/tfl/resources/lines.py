"""``client.lines``: line status and disruptions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, get_args

from pydantic import TypeAdapter

from .._core import Endpoint, ParamValue
from ..models.lines import Disruption, LineStatus, RouteSequence
from ._params import csv, segment

if TYPE_CHECKING:
    from ..client import AsyncTflClient, TflClient

#: Which way along a line: TfL's ``inbound`` or ``outbound``.
Direction = Literal["inbound", "outbound"]

_line_statuses = TypeAdapter(list[LineStatus])
_disruptions = TypeAdapter(list[Disruption])


# --------------------------------------------------------------------------- endpoint specs


def _status_endpoint(modes: str | Sequence[str]) -> Endpoint[list[LineStatus]]:
    if not modes:
        raise ValueError("modes must name at least one mode, e.g. 'tube'")
    return Endpoint(f"/Line/Mode/{segment(csv(modes))}/Status", _line_statuses.validate_python)


def _disruptions_endpoint(line_id: str) -> Endpoint[list[Disruption]]:
    return Endpoint(f"/Line/{segment(line_id)}/Disruption", _disruptions.validate_python)


def _route_sequence_endpoint(
    line_id: str, direction: Direction, service_types: str | Sequence[str]
) -> Endpoint[RouteSequence]:
    if direction not in get_args(Direction):
        raise ValueError(f"direction must be one of {get_args(Direction)}")
    params: dict[str, ParamValue] = {"serviceTypes": csv(service_types)} if service_types else {}
    return Endpoint(
        f"/Line/{segment(line_id)}/Route/Sequence/{direction}",
        RouteSequence.model_validate,
        params,
        cacheable=True,
    )


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

    def route_sequence(
        self, line_id: str, direction: Direction, service_types: str | Sequence[str] = ()
    ) -> RouteSequence:
        """Fetch a line's routes in one direction, each as its stops in calling order.

        Args:
            line_id: A line id such as ``"central"``.
            direction: ``"inbound"`` or ``"outbound"``.
            service_types: ``"Regular"``, ``"Night"`` or both. Empty means TfL's default
                (regular service).

        Returns:
            The line's routes (one per branch combination) and its stations. Cached when
            the client cache is on.

        Raises:
            ValueError: If ``direction`` is not ``"inbound"`` or ``"outbound"``.
            TflNotFoundError: If the line id is not recognised.

        """
        return self._client._execute(_route_sequence_endpoint(line_id, direction, service_types))


class AsyncLines:
    """Line endpoints for :class:`~tfl.AsyncTflClient`. See :class:`Lines`."""

    def __init__(self, client: AsyncTflClient) -> None:
        self._client = client

    async def status(self, modes: str | Sequence[str] = ("tube",)) -> list[LineStatus]:
        """Fetch the current status of every line on the given modes. Never cached.

        Args:
            modes: One mode or several, e.g. ``"tube"`` or ``("tube", "dlr")``.

        Returns:
            One entry per line, each with its current ``statuses`` (usually one).

        Raises:
            ValueError: If ``modes`` is empty.

        """
        return await self._client._execute(_status_endpoint(modes))

    async def disruptions(self, line_id: str) -> list[Disruption]:
        """Fetch current disruptions on a line. Never cached.

        Args:
            line_id: A line id such as ``"central"``.

        Returns:
            The disruptions; empty when the line has none.

        """
        return await self._client._execute(_disruptions_endpoint(line_id))

    async def route_sequence(
        self, line_id: str, direction: Direction, service_types: str | Sequence[str] = ()
    ) -> RouteSequence:
        """Fetch a line's routes in one direction, each as its stops in calling order.

        Args:
            line_id: A line id such as ``"central"``.
            direction: ``"inbound"`` or ``"outbound"``.
            service_types: ``"Regular"``, ``"Night"`` or both. Empty means TfL's default
                (regular service).

        Returns:
            The line's routes (one per branch combination) and its stations. Cached when
            the client cache is on.

        Raises:
            ValueError: If ``direction`` is not ``"inbound"`` or ``"outbound"``.
            TflNotFoundError: If the line id is not recognised.

        """
        return await self._client._execute(
            _route_sequence_endpoint(line_id, direction, service_types)
        )

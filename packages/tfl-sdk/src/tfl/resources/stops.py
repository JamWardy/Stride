"""``client.stops``: stop points, nearby search and live arrivals."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from pydantic import TypeAdapter

from .._core import Endpoint, ParamValue
from ..models.stops import Arrival, NearbyStop, Stop, StopSummary

if TYPE_CHECKING:
    from ..client import AsyncTflClient, TflClient

_stop_summaries = TypeAdapter(list[StopSummary])
_nearby_stops = TypeAdapter(list[NearbyStop])
_arrivals = TypeAdapter(list[Arrival])


def _segment(value: str) -> str:
    """Percent-encode a value used as a single URL path segment."""
    return quote(value, safe="")


def _csv(values: str | Sequence[str]) -> str:
    """Join values with commas; a single string is treated as one value, not as characters."""
    return values if isinstance(values, str) else ",".join(values)


# --------------------------------------------------------------------------- endpoint specs


def _parse_search(raw: Any) -> list[StopSummary]:
    return _stop_summaries.validate_python(raw.get("matches") or [])


def _parse_nearby(raw: Any) -> list[NearbyStop]:
    return _nearby_stops.validate_python(raw.get("stopPoints") or [])


def _parse_arrivals(raw: Any) -> list[Arrival]:
    return sorted(_arrivals.validate_python(raw), key=lambda a: a.time_to_station)


def _search_endpoint(query: str, modes: str | Sequence[str]) -> Endpoint[list[StopSummary]]:
    params = {"modes": _csv(modes)} if modes else {}
    return Endpoint(f"/StopPoint/Search/{_segment(query)}", _parse_search, params, cacheable=True)


def _nearby_endpoint(
    lat: float, lon: float, radius_m: int, stop_types: str | Sequence[str]
) -> Endpoint[list[NearbyStop]]:
    params: dict[str, ParamValue] = {
        "lat": lat,
        "lon": lon,
        "radius": radius_m,
        "stopTypes": _csv(stop_types),
    }
    return Endpoint("/StopPoint", _parse_nearby, params)


def _get_endpoint(stop_id: str) -> Endpoint[Stop]:
    return Endpoint(f"/StopPoint/{_segment(stop_id)}", Stop.model_validate, cacheable=True)


def _arrivals_endpoint(stop_id: str) -> Endpoint[list[Arrival]]:
    return Endpoint(f"/StopPoint/{_segment(stop_id)}/Arrivals", _parse_arrivals)


# --------------------------------------------------------------------------- resources


class Stops:
    """Stop-point endpoints for :class:`~tfl.TflClient`."""

    def __init__(self, client: TflClient) -> None:
        self._client = client

    def search(self, query: str, modes: str | Sequence[str] = ("tube",)) -> list[StopSummary]:
        """Search stops by name.

        Args:
            query: Free text, e.g. ``"Oxford Circus"``.
            modes: Only return stops served by these modes, e.g. ``"bus"`` or
                ``("tube", "dlr")``. Pass an empty tuple for all modes.

        Returns:
            Matching stops, in TfL's relevance order. Cached when the client cache is on.

        """
        return self._client._execute(_search_endpoint(query, modes))

    def nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int = 800,
        stop_types: str | Sequence[str] = ("NaptanMetroStation",),
    ) -> list[NearbyStop]:
        """Find stops within ``radius_m`` metres of a point.

        Args:
            lat: Latitude (WGS84).
            lon: Longitude (WGS84).
            radius_m: Search radius in metres.
            stop_types: One NaPTAN stop type or several, e.g. ``"NaptanMetroStation"``,
                ``"NaptanPublicBusCoachTram"``, ``"NaptanRailStation"``.

        Returns:
            Stops in TfL's order (nearest first), each with ``distance_m``.

        """
        return self._client._execute(_nearby_endpoint(lat, lon, radius_m, stop_types))

    def get(self, stop_id: str) -> Stop:
        """Fetch one stop, including its lines and child stops (platforms, entrances).

        Args:
            stop_id: A NaPTAN id such as ``"940GZZLUOXC"``.

        Raises:
            TflNotFoundError: If the stop id is not recognised.

        """
        return self._client._execute(_get_endpoint(stop_id))

    def arrivals(self, stop_id: str) -> list[Arrival]:
        """Fetch live arrival predictions for a stop, soonest first. Never cached.

        Args:
            stop_id: A NaPTAN id such as ``"940GZZLUOXC"``.

        """
        return self._client._execute(_arrivals_endpoint(stop_id))


class AsyncStops:
    """Stop-point endpoints for :class:`~tfl.AsyncTflClient`. See :class:`Stops`."""

    def __init__(self, client: AsyncTflClient) -> None:
        self._client = client

    async def search(self, query: str, modes: str | Sequence[str] = ("tube",)) -> list[StopSummary]:
        """Search stops by name. See :meth:`Stops.search`."""
        return await self._client._execute(_search_endpoint(query, modes))

    async def nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int = 800,
        stop_types: str | Sequence[str] = ("NaptanMetroStation",),
    ) -> list[NearbyStop]:
        """Find stops within ``radius_m`` metres of a point. See :meth:`Stops.nearby`."""
        return await self._client._execute(_nearby_endpoint(lat, lon, radius_m, stop_types))

    async def get(self, stop_id: str) -> Stop:
        """Fetch one stop. See :meth:`Stops.get`."""
        return await self._client._execute(_get_endpoint(stop_id))

    async def arrivals(self, stop_id: str) -> list[Arrival]:
        """Fetch live arrivals for a stop, soonest first. See :meth:`Stops.arrivals`."""
        return await self._client._execute(_arrivals_endpoint(stop_id))

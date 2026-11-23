"""``client.journeys``: the journey planner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import TypeAdapter, ValidationError

from .._core import Endpoint, ParamValue, error_details, json_list
from ..errors import TflAmbiguousLocationError, TflError
from ..models._base import LONDON
from ..models.journeys import Journey, LocationOption
from ._params import segment

if TYPE_CHECKING:
    from ..client import AsyncTflClient, TflClient

_journeys = TypeAdapter(list[Journey])
_location_options = TypeAdapter(list[LocationOption])


# --------------------------------------------------------------------------- endpoint specs


def _parse_journeys(raw: Any) -> list[Journey]:
    return _journeys.validate_python(json_list(raw, "journeys"))


def _options(body: dict[str, Any], key: str) -> list[LocationOption]:
    section = body.get(key)
    if not isinstance(section, dict):
        return []
    return _location_options.validate_python(section.get("disambiguationOptions") or [])


def _ambiguity_parser(from_: str, to: str) -> Callable[[httpx.Response], TflError | None]:
    """Build the hook that turns the planner's 300 reply into TflAmbiguousLocationError."""

    def parse(response: httpx.Response) -> TflError | None:
        if response.status_code != 300:
            return None
        details = error_details(response)
        body = details["body"]
        if not isinstance(body, dict):
            return None
        try:
            from_options = _options(body, "fromLocationDisambiguation")
            to_options = _options(body, "toLocationDisambiguation")
            via_options = _options(body, "viaLocationDisambiguation")
        except ValidationError:
            return None
        unclear = [
            f"{label} ({len(options)} options)"
            for label, options in (
                (f"from {from_!r}", from_options),
                (f"to {to!r}", to_options),
                ("via", via_options),
            )
            if options
        ]
        message = "Ambiguous journey location: " + (", ".join(unclear) or "no options given")
        return TflAmbiguousLocationError(
            message,
            from_options=from_options,
            to_options=to_options,
            via_options=via_options,
            **details,
        )

    return parse


def _plan_endpoint(from_: str, to: str, depart_at: datetime | None) -> Endpoint[list[Journey]]:
    params: dict[str, ParamValue] = {}
    if depart_at is not None:
        local = (
            depart_at.replace(tzinfo=LONDON)
            if depart_at.tzinfo is None
            else depart_at.astimezone(LONDON)
        )
        params = {
            "date": local.strftime("%Y%m%d"),
            "time": local.strftime("%H%M"),
            "timeIs": "Departing",
        }
    return Endpoint(
        f"/Journey/JourneyResults/{segment(from_)}/to/{segment(to)}",
        _parse_journeys,
        params,
        parse_error=_ambiguity_parser(from_, to),
    )


# --------------------------------------------------------------------------- resources


class Journeys:
    """Journey-planner endpoints for :class:`~tfl.TflClient`."""

    def __init__(self, client: TflClient) -> None:
        self._client = client

    def plan(self, from_: str, to: str, *, depart_at: datetime | None = None) -> list[Journey]:
        """Plan journeys between two places. Never cached.

        Args:
            from_: Where to start: a stop id (``"940GZZLUOXC"``), an ICS code, a place name,
                a postcode or ``"lat,lon"``.
            to: Where to go, in any of the same forms.
            depart_at: When to leave. Naive datetimes are read as London time; ``None``
                means now.

        Returns:
            TfL's journey options, in the order TfL gives them.

        Raises:
            TflAmbiguousLocationError: If ``from_`` or ``to`` matches several places; the
                error lists the candidates.

        """
        return self._client._execute(_plan_endpoint(from_, to, depart_at))


class AsyncJourneys:
    """Journey-planner endpoints for :class:`~tfl.AsyncTflClient`. See :class:`Journeys`."""

    def __init__(self, client: AsyncTflClient) -> None:
        self._client = client

    async def plan(
        self, from_: str, to: str, *, depart_at: datetime | None = None
    ) -> list[Journey]:
        """Plan journeys between two places. Never cached.

        Args:
            from_: Where to start: a stop id (``"940GZZLUOXC"``), an ICS code, a place name,
                a postcode or ``"lat,lon"``.
            to: Where to go, in any of the same forms.
            depart_at: When to leave. Naive datetimes are read as London time; ``None``
                means now.

        Returns:
            TfL's journey options, in the order TfL gives them.

        Raises:
            TflAmbiguousLocationError: If ``from_`` or ``to`` matches several places; the
                error lists the candidates.

        """
        return await self._client._execute(_plan_endpoint(from_, to, depart_at))

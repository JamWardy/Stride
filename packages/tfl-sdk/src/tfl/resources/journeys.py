"""``client.journeys``: the journey planner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, get_args

import httpx
from pydantic import TypeAdapter, ValidationError

from .._core import Endpoint, ParamValue, error_details, json_list
from ..errors import TflAmbiguousLocationError, TflError
from ..models._base import LONDON
from ..models.journeys import Journey, LocationOption
from ._params import csv, segment

if TYPE_CHECKING:
    from ..client import AsyncTflClient, TflClient

#: TfL's walking-speed setting for the journey planner.
WalkingSpeed = Literal["slow", "average", "fast"]

_journeys = TypeAdapter(list[Journey])
_location_options = TypeAdapter(list[LocationOption])


# --------------------------------------------------------------------------- endpoint specs


def _parse_journeys(raw: Any) -> list[Journey]:
    return _journeys.validate_python(json_list(raw, "journeys"))


def _options(body: Any, key: str) -> list[LocationOption]:
    """Return the candidates under ``key``, or ``[]`` if missing or not in the expected shape."""
    section = body.get(key) if isinstance(body, dict) else None
    if not isinstance(section, dict):
        return []
    try:
        return _location_options.validate_python(section.get("disambiguationOptions") or [])
    except ValidationError:
        return []


def _ambiguity_parser(from_: str, to: str) -> Callable[[httpx.Response], TflError | None]:
    """Build the hook that turns the planner's 300 reply into TflAmbiguousLocationError."""

    def parse(response: httpx.Response) -> TflError | None:
        if response.status_code != 300:
            return None
        details = error_details(response)
        body = details["body"]
        from_options = _options(body, "fromLocationDisambiguation")
        to_options = _options(body, "toLocationDisambiguation")
        via_options = _options(body, "viaLocationDisambiguation")
        unclear = [
            f"{label} ({len(options)} options)"
            for label, options in (
                (f"from {from_!r}", from_options),
                (f"to {to!r}", to_options),
                ("via", via_options),
            )
            if options
        ]
        listed = ", ".join(unclear) or "TfL gave no readable options"
        message = f"Ambiguous journey location: {listed}"
        return TflAmbiguousLocationError(
            message,
            from_options=from_options,
            to_options=to_options,
            via_options=via_options,
            **details,
        )

    return parse


def _plan_endpoint(
    from_: str,
    to: str,
    depart_at: datetime | None,
    modes: str | Sequence[str],
    walking_speed: WalkingSpeed | None,
) -> Endpoint[list[Journey]]:
    params: dict[str, ParamValue] = {}
    if modes:
        params["mode"] = csv(modes)
    if walking_speed is not None:
        if walking_speed not in get_args(WalkingSpeed):
            raise ValueError(f"walking_speed must be one of {get_args(WalkingSpeed)}")
        params["walkingSpeed"] = walking_speed
    if depart_at is not None:
        local = (
            depart_at.replace(tzinfo=LONDON)
            if depart_at.tzinfo is None
            else depart_at.astimezone(LONDON)
        )
        params["date"] = local.strftime("%Y%m%d")
        params["time"] = local.strftime("%H%M")
        params["timeIs"] = "Departing"
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

    def plan(
        self,
        from_: str,
        to: str,
        *,
        depart_at: datetime | None = None,
        modes: str | Sequence[str] = (),
        walking_speed: WalkingSpeed | None = None,
    ) -> list[Journey]:
        """Plan journeys between two places. Never cached.

        Args:
            from_: Where to start: a stop id (``"940GZZLUOXC"``), an ICS code, a place name,
                a postcode or ``"lat,lon"``.
            to: Where to go, in any of the same forms.
            depart_at: When to leave. Naive datetimes are read as London time; ``None``
                means now.
            modes: Only use these modes, e.g. ``("tube", "dlr", "walking")``. Include
                ``"walking"`` for walks to and from stations. Empty means TfL's default.
            walking_speed: TfL's walking pace, ``"slow"``, ``"average"`` or ``"fast"``.
                ``None`` means TfL's default.

        Returns:
            TfL's journey options, in the order TfL gives them.

        Raises:
            TflAmbiguousLocationError: If ``from_`` or ``to`` matches several places; the
                error lists the candidates.
            ValueError: If ``walking_speed`` is not one of the three settings.

        """
        return self._client._execute(_plan_endpoint(from_, to, depart_at, modes, walking_speed))


class AsyncJourneys:
    """Journey-planner endpoints for :class:`~tfl.AsyncTflClient`. See :class:`Journeys`."""

    def __init__(self, client: AsyncTflClient) -> None:
        self._client = client

    async def plan(
        self,
        from_: str,
        to: str,
        *,
        depart_at: datetime | None = None,
        modes: str | Sequence[str] = (),
        walking_speed: WalkingSpeed | None = None,
    ) -> list[Journey]:
        """Plan journeys between two places. Never cached.

        Args:
            from_: Where to start: a stop id (``"940GZZLUOXC"``), an ICS code, a place name,
                a postcode or ``"lat,lon"``.
            to: Where to go, in any of the same forms.
            depart_at: When to leave. Naive datetimes are read as London time; ``None``
                means now.
            modes: Only use these modes, e.g. ``("tube", "dlr", "walking")``. Include
                ``"walking"`` for walks to and from stations. Empty means TfL's default.
            walking_speed: TfL's walking pace, ``"slow"``, ``"average"`` or ``"fast"``.
                ``None`` means TfL's default.

        Returns:
            TfL's journey options, in the order TfL gives them.

        Raises:
            TflAmbiguousLocationError: If ``from_`` or ``to`` matches several places; the
                error lists the candidates.
            ValueError: If ``walking_speed`` is not one of the three settings.

        """
        return await self._client._execute(
            _plan_endpoint(from_, to, depart_at, modes, walking_speed)
        )

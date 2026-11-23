"""Models for ``/Line`` endpoints."""

from __future__ import annotations

import html
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from ._base import OptionalStr, OptionalTflDatetime, TflDatetime, TflModel
from .stops import StopSummary


def _clean_name(value: Any) -> Any:
    """``"Ealing Broadway  &harr;  Epping "`` -> ``"Ealing Broadway ↔ Epping"``."""
    return " ".join(html.unescape(value).split()) if isinstance(value, str) else value


class Disruption(TflModel):
    """A disruption notice for a line or stop.

    ``summary``, ``additional_info``, ``created`` and ``last_update`` are only sent by the
    journey planner; ``/Line/{id}/Disruption`` leaves them out.
    """

    category: OptionalStr = None
    type: OptionalStr = None
    category_description: OptionalStr = None
    description: OptionalStr = None
    summary: OptionalStr = None
    additional_info: OptionalStr = None
    created: OptionalTflDatetime = None
    last_update: OptionalTflDatetime = None


class ValidityPeriod(TflModel):
    """When a status applies."""

    from_date: TflDatetime
    to_date: TflDatetime
    is_now: bool = False


class ServiceStatus(TflModel):
    """One status entry for a line, e.g. ``Minor Delays`` with the reason."""

    severity: int = Field(alias="statusSeverity")
    """TfL's severity code; 10 is ``Good Service``."""
    description: str = Field(alias="statusSeverityDescription")
    reason: OptionalStr = None
    validity_periods: list[ValidityPeriod] = Field(default_factory=list)
    disruption: Disruption | None = None


class LineStatus(TflModel):
    """A line and its current status (``/Line/Mode/{modes}/Status``)."""

    id: str
    name: str
    mode_name: str
    statuses: list[ServiceStatus] = Field(default_factory=list, alias="lineStatuses")


class OrderedRoute(TflModel):
    """One way a train can run along a line, as its stops in calling order.

    Branches are separate routes, e.g. ``"Morden ↔ Edgware via Bank"`` and
    ``"Morden ↔ Edgware via Charing Cross"``.
    """

    name: Annotated[str, BeforeValidator(_clean_name)]
    stop_ids: list[str] = Field(default_factory=list, alias="naptanIds")
    service_type: OptionalStr = None


class RouteSequence(TflModel):
    """The routes of a line in one direction, from ``/Line/{id}/Route/Sequence/{direction}``.

    Each route's ``stop_ids`` run in the requested direction, first stop to terminus, and
    use the same stop ids as arrivals and journey legs (e.g. ``940GZZLUBNK``). ``stations``
    lists interchange stations by their hub id instead (e.g. ``HUBBAN`` for Bank).
    """

    line_id: str
    line_name: str
    direction: str
    mode: OptionalStr = None
    is_outbound_only: bool = False
    routes: list[OrderedRoute] = Field(default_factory=list, alias="orderedLineRoutes")
    stations: list[StopSummary] = Field(default_factory=list)

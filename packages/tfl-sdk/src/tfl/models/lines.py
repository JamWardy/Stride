"""Models for ``/Line`` endpoints."""

from __future__ import annotations

from pydantic import Field

from ._base import OptionalStr, OptionalTflDatetime, TflDatetime, TflModel


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

"""Models for ``/StopPoint`` endpoints."""

from __future__ import annotations

from pydantic import Field

from ._base import OptionalStr, OptionalTflDatetime, TflDatetime, TflModel


class StopSummary(TflModel):
    """A stop returned by a text search (``/StopPoint/Search``)."""

    id: str
    name: str
    lat: float
    lon: float
    modes: list[str] = Field(default_factory=list)
    zone: OptionalStr = None
    ics_id: OptionalStr = None
    top_most_parent_id: OptionalStr = None


class LineRef(TflModel):
    """A reference to a line serving a stop."""

    id: str
    name: str


class LineModeGroup(TflModel):
    """The lines of one mode serving a stop."""

    mode_name: str
    line_ids: list[str] = Field(default_factory=list, alias="lineIdentifier")


class AdditionalProperty(TflModel):
    """A free-form key/value attribute of a stop (facilities, address, opening times...)."""

    category: OptionalStr = None
    key: OptionalStr = None
    value: OptionalStr = None


class Stop(TflModel):
    """A stop point, e.g. a station, platform or entrance.

    ``lat``/``lon`` are ``0.0`` for some child stops (platforms), as returned by TfL.
    """

    id: str
    name: str = Field(alias="commonName")
    lat: float
    lon: float
    naptan_id: OptionalStr = None
    station_naptan: OptionalStr = None
    stop_type: OptionalStr = None
    ics_code: OptionalStr = None
    modes: list[str] = Field(default_factory=list)
    lines: list[LineRef] = Field(default_factory=list)
    line_mode_groups: list[LineModeGroup] = Field(default_factory=list)
    additional_properties: list[AdditionalProperty] = Field(default_factory=list)
    children: list[Stop] = Field(default_factory=list)


class NearbyStop(Stop):
    """A stop returned by a location search, with its straight-line distance from the point."""

    distance_m: float = Field(alias="distance")


class Arrival(TflModel):
    """A live arrival prediction for a vehicle at a stop."""

    id: str
    line_id: str
    line_name: str
    expected_arrival: TflDatetime
    time_to_station: int
    """Seconds until the vehicle is expected at the stop."""
    platform_name: OptionalStr = None
    direction: OptionalStr = None
    destination_name: OptionalStr = None
    destination_naptan_id: OptionalStr = None
    towards: OptionalStr = None
    current_location: OptionalStr = None
    stop_id: OptionalStr = Field(default=None, alias="naptanId")
    station_name: OptionalStr = None
    vehicle_id: OptionalStr = None
    mode_name: OptionalStr = None
    timestamp: OptionalTflDatetime = None

    @property
    def minutes_away(self) -> int:
        """Whole minutes until arrival, rounded down (0 means due)."""
        return self.time_to_station // 60

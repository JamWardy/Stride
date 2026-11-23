"""Models for ``/Journey/JourneyResults``."""

from __future__ import annotations

from pydantic import Field

from ._base import OptionalStr, OptionalTflDatetime, TflDatetime, TflModel
from .lines import Disruption
from .stops import LineRef


class Place(TflModel):
    """A place: a journey leg's start or end, or a candidate in a disambiguation list.

    Only ``name``, ``lat`` and ``lon`` are always present. Stop points also carry
    ``naptan_id`` and ``ics_code``; ``platform_name`` comes only on journey legs, and
    ``modes``/``stop_type`` only on disambiguation candidates.
    """

    name: str = Field(alias="commonName")
    lat: float
    lon: float
    place_type: OptionalStr = None
    naptan_id: OptionalStr = None
    ics_code: OptionalStr = None
    platform_name: OptionalStr = None
    stop_type: OptionalStr = None
    modes: list[str] = Field(default_factory=list)


class LocationOption(TflModel):
    """One candidate TfL offers when a journey's start, end or via point is ambiguous."""

    parameter_value: str
    """Pass this back as ``from_``/``to`` to plan with this candidate."""
    place: Place
    match_quality: int | None = None


class InstructionStep(TflModel):
    """One turn-by-turn step of a walking leg, e.g. "Turn left on to Baker Street"."""

    description_heading: OptionalStr = None
    description: OptionalStr = None
    street_name: OptionalStr = None
    turn_direction: OptionalStr = None
    distance_m: float | None = Field(default=None, alias="distance")
    lat: float | None = Field(default=None, alias="latitude")
    lon: float | None = Field(default=None, alias="longitude")


class Instruction(TflModel):
    """Human-readable directions for a leg; ``steps`` only on walking legs."""

    summary: str
    detailed: OptionalStr = None
    steps: list[InstructionStep] = Field(default_factory=list)


class StopRef(TflModel):
    """A stop on a leg's path.

    ``id`` is ``None`` when TfL leaves it out, as it does for the station at the end of a
    walk between two stations.
    """

    id: OptionalStr = None
    name: str


class LegPath(TflModel):
    """Where a leg goes.

    ``stops`` lists the calls after boarding, ending at the stop where you get off; it is
    empty for walking legs.
    """

    stops: list[StopRef] = Field(default_factory=list, alias="stopPoints")


class ModeRef(TflModel):
    """The transport mode of a leg, e.g. ``tube`` or ``walking``."""

    id: str
    name: str


class RouteOption(TflModel):
    """A line (and direction) that can be used for a leg."""

    name: str
    directions: list[str] = Field(default_factory=list)
    direction: OptionalStr = None
    line: LineRef | None = Field(default=None, alias="lineIdentifier")


class Leg(TflModel):
    """One part of a journey on a single mode."""

    duration_minutes: int = Field(alias="duration")
    distance_m: float | None = Field(default=None, alias="distance")
    """Metres on walking legs. On other legs TfL's value is not metres (36 for a two-stop
    Tube ride), so only rely on it for walking."""
    instruction: Instruction
    mode: ModeRef
    departure_time: TflDatetime
    arrival_time: TflDatetime
    departure_point: Place
    arrival_point: Place
    scheduled_departure_time: OptionalTflDatetime = None
    scheduled_arrival_time: OptionalTflDatetime = None
    route_options: list[RouteOption] = Field(default_factory=list)
    path: LegPath | None = None
    disruptions: list[Disruption] = Field(default_factory=list)
    is_disrupted: bool = False


class Fare(TflModel):
    """The fare for a whole journey."""

    total_cost_pence: int = Field(alias="totalCost")


class Journey(TflModel):
    """One journey option from the journey planner."""

    start_time: TflDatetime = Field(alias="startDateTime")
    arrival_time: TflDatetime = Field(alias="arrivalDateTime")
    duration_minutes: int = Field(alias="duration")
    legs: list[Leg] = Field(default_factory=list)
    fare: Fare | None = None

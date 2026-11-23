"""Pure option logic: which trains a walker can catch. No HTTP here.

The pipeline is ``catchable_options`` → ``best_per_line_direction``. A future filter (e.g.
"only trains heading towards my destination") slots in as another step on the list of
:class:`WalkOption` that :func:`build_options` returns.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from tfl import Arrival


@dataclass(frozen=True)
class ReachableStation:
    """A station within walking range, with the estimated walk and street-to-platform time."""

    id: str
    name: str
    walk_seconds: float
    entry_buffer_seconds: float


@dataclass(frozen=True)
class WalkOption:
    """A train the walker can catch by leaving now.

    ``wait_seconds`` is the time spent on the platform before the train arrives.
    ``margin_seconds`` is the slack left after the risk setting's safety margin, i.e. how
    much later the walker could leave and still make it at their chosen risk.
    """

    station_id: str
    station_name: str
    line_id: str
    line_name: str
    direction: str | None
    destination_name: str | None
    platform_name: str | None
    departure_time: datetime
    walk_seconds: float
    wait_seconds: float
    margin_seconds: float

    @property
    def walk_minutes(self) -> float:
        """Walking time in minutes."""
        return self.walk_seconds / 60

    @property
    def wait_minutes(self) -> float:
        """Time on the platform in minutes."""
        return self.wait_seconds / 60

    @property
    def can_make_it(self) -> bool:
        """True when the train is reachable with the safety margin to spare."""
        return self.margin_seconds >= 0


def catchable_options(
    station: ReachableStation, arrivals: Iterable[Arrival], safety_margin_s: float
) -> list[WalkOption]:
    """Return an option for each arrival the walker can reach in time.

    A train is catchable when ``walk + entry_buffer + safety_margin <= time_to_station``.
    Trains that terminate at this station are skipped: they go nowhere from here.
    """
    reach_platform_s = station.walk_seconds + station.entry_buffer_seconds
    options = []
    for arrival in arrivals:
        if arrival.destination_naptan_id == station.id:
            continue
        wait = arrival.time_to_station - reach_platform_s
        margin = wait - safety_margin_s
        if margin < 0:
            continue
        options.append(
            WalkOption(
                station_id=station.id,
                station_name=station.name,
                line_id=arrival.line_id,
                line_name=arrival.line_name,
                direction=arrival.direction,
                destination_name=arrival.destination_name,
                platform_name=arrival.platform_name,
                departure_time=arrival.expected_arrival,
                walk_seconds=station.walk_seconds,
                wait_seconds=wait,
                margin_seconds=margin,
            )
        )
    return options


def best_per_line_direction(options: Iterable[WalkOption]) -> list[WalkOption]:
    """Keep the earliest train per station, line and direction, sorted by departure time."""
    ordered = sorted(options, key=lambda o: (o.departure_time, o.walk_seconds))
    seen: set[tuple[str, str, str | None]] = set()
    best = []
    for option in ordered:
        key = (option.station_id, option.line_id, option.direction)
        if key not in seen:
            seen.add(key)
            best.append(option)
    return best


def build_options(
    stations: Sequence[ReachableStation],
    arrivals_by_station: Mapping[str, Sequence[Arrival]],
    safety_margin_s: float,
) -> list[WalkOption]:
    """Combine stations and their live arrivals into deduplicated, sorted options."""
    options = [
        option
        for station in stations
        for option in catchable_options(
            station, arrivals_by_station.get(station.id, ()), safety_margin_s
        )
    ]
    return best_per_line_direction(options)

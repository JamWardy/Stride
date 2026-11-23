"""Pure journey logic: re-time TfL's routes at the walker's own pace against live trains.

No HTTP here. :func:`build_journey_options` takes TfL's journey plans, live arrivals and line
route sequences, all fetched elsewhere, and works out which trains the walker can catch.

How each part of a route is timed:

- **Walks:** the street part is ``Leg.distance_m`` at the walker's speed. The station part
  (street to platform, or platform to street) is what TfL's walk leg takes beyond its street
  walk at TfL's pace, scaled from TfL's pace to the walker's. Per-station overrides win.
- **Changes between trains:** TfL has no walk leg for these. The smallest gap at a station
  across TfL's journeys is taken as its change time, scaled the same way.
- **Trains:** the first live train on one of the leg's lines that calls at the stop where
  the walker gets off and that they can reach with the risk setting's safety margin.
  Without one (e.g. beyond the live horizon), the earliest such departure in TfL's
  timetabled journeys. Time on the train is TfL's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Literal

from tfl import Arrival, Journey, Leg, OrderedRoute, WalkingSpeed

from .walking import TFL_PACE_KMH, WalkerProfile

#: TfL modes used for journeys: rail modes with live arrivals, plus walking.
DEFAULT_MODES = ("tube", "dlr", "overground", "elizabeth-line", "walking")


@dataclass(frozen=True)
class WalkLeg:
    """A walk: along streets, and through a station at either end if there is one."""

    from_name: str
    to_name: str
    distance_m: float
    street_seconds: float
    station_seconds: float
    seconds: float
    kind: Literal["walk"] = "walk"


@dataclass(frozen=True)
class ChangeLeg:
    """Changing trains inside a station (platform to platform)."""

    stop_id: str
    name: str
    seconds: float
    kind: Literal["change"] = "change"


@dataclass(frozen=True)
class TrainLeg:
    """A train to catch.

    ``wait_seconds`` is the time on the platform before it comes. ``margin_seconds`` is the
    slack left after the risk setting's safety margin. ``source`` says whether the train
    came from live arrivals or from TfL's timetable.
    """

    line_id: str
    line_name: str
    from_stop_id: str
    from_name: str
    to_stop_id: str
    to_name: str
    destination_name: str | None
    platform_name: str | None
    departure_time: datetime
    arrival_time: datetime
    wait_seconds: float
    margin_seconds: float
    source: Literal["live", "timetable"]
    kind: Literal["train"] = "train"


JourneyLeg = WalkLeg | ChangeLeg | TrainLeg


@dataclass(frozen=True)
class JourneyOption:
    """One way to get there, timed for this walker, leaving now.

    ``leave_by`` is the latest time to set off and still catch the first train.
    ``margin_seconds`` is the smallest margin across every train to catch, i.e. how tight
    the tightest connection is; ``None`` for a walk with no trains.
    """

    leave_by: datetime
    arrival_time: datetime
    legs: tuple[JourneyLeg, ...]
    margin_seconds: float | None


@dataclass(frozen=True)
class MissingTrain:
    """A train leg with no data: no live train or timetabled departure late enough.

    Fetch TfL's timetable for ``board`` → ``alight`` departing at ``ready_at`` (e.g. with
    ``journeys.plan``) and pass it back as ``extra_timetable``.
    """

    board: str
    alight: str
    ready_at: datetime


@dataclass(frozen=True)
class JourneyBuild:
    """What :func:`build_journey_options` found: the options, and any hops it lacked data for.

    A journey with a hop in ``missing`` is left out of ``options``.
    """

    options: list[JourneyOption]
    missing: list[MissingTrain]


@dataclass(frozen=True)
class JourneyContext:
    """Everything :func:`retime` needs besides the journey itself."""

    profile: WalkerProfile
    tfl_setting: WalkingSpeed
    now: datetime
    arrivals_by_stop: Mapping[str, Sequence[Arrival]]
    routes_by_line: Mapping[str, Sequence[OrderedRoute]]
    timetable: Mapping[tuple[str, str], Sequence[Leg]]
    change_seconds: Mapping[str, float]
    entry_buffers: Mapping[str, float]
    default_entry_buffer_s: float

    @property
    def pace_ratio(self) -> float:
        """TfL's pace over the walker's: multiply TfL's walking times by this."""
        return TFL_PACE_KMH[self.tfl_setting] / self.profile.walking_speed_kmh


# --------------------------------------------------------------------------- building blocks


def is_train(leg: Leg) -> bool:
    """Return True for any leg that isn't a walk."""
    return leg.mode.id != "walking"


def leg_lines(leg: Leg) -> set[str]:
    """Line ids that can be used for a leg."""
    return {option.line.id for option in leg.route_options if option.line is not None}


def calls_at(routes: Iterable[OrderedRoute], board: str, alight: str, terminus: str) -> bool:
    """Return True if some route runs ``board`` → ``alight`` → ``terminus`` in that order.

    ``terminus`` may be ``alight`` itself. A train to a terminus before ``alight``, or going
    the other way, does not count.
    """
    for route in routes:
        ids = route.stop_ids
        try:
            i = ids.index(board)
            j = ids.index(alight, i + 1)
            ids.index(terminus, j)
        except ValueError:
            continue
        return True
    return False


def tfl_station_seconds(leg: Leg, tfl_setting: WalkingSpeed) -> float:
    """Seconds TfL allows for the station part of a walk leg, at TfL's pace.

    That is the leg's duration beyond its street walk at TfL's pace. Walks that touch no
    station have no station part.
    """
    if leg.distance_m is None or not (leg.departure_point.naptan_id or leg.arrival_point.naptan_id):
        return 0.0
    street_s = leg.distance_m / (TFL_PACE_KMH[tfl_setting] / 3.6)
    return max(0.0, leg.duration_minutes * 60 - street_s)


def walk_leg(leg: Leg, ctx: JourneyContext) -> WalkLeg:
    """Time a TfL walk leg at the walker's pace."""
    if leg.distance_m is None:  # no distance: scale TfL's whole time
        street_s = leg.duration_minutes * 60 * ctx.pace_ratio
        distance = street_s * ctx.profile.speed_m_s
    else:
        distance = leg.distance_m
        street_s = distance / ctx.profile.speed_m_s
    stations = [p.naptan_id for p in (leg.departure_point, leg.arrival_point) if p.naptan_id]
    if stations and all(s in ctx.entry_buffers for s in stations):
        station_s = sum(ctx.entry_buffers[s] for s in stations)
    else:
        station_s = tfl_station_seconds(leg, ctx.tfl_setting) * ctx.pace_ratio
    return WalkLeg(
        from_name=leg.departure_point.name,
        to_name=leg.arrival_point.name,
        distance_m=distance,
        street_seconds=street_s,
        station_seconds=station_s,
        seconds=street_s + station_s,
    )


def tfl_change_seconds(journeys: Iterable[Journey]) -> dict[str, float]:
    """Return the smallest gap between two consecutive trains at each station.

    Keyed by the stop where the walker gets off the first train. TfL's gap includes any
    wait for the next train, so the smallest one is the best estimate of the change time.
    """
    gaps: dict[str, float] = {}
    for journey in journeys:
        for a, b in pairwise(journey.legs):
            stop = a.arrival_point.naptan_id
            if not (is_train(a) and is_train(b)) or stop is None:
                continue
            gap = (b.departure_time - a.arrival_time).total_seconds()
            gaps[stop] = min(gap, gaps.get(stop, gap))
    return gaps


def timetable_index(journeys: Iterable[Journey]) -> dict[tuple[str, str], list[Leg]]:
    """TfL's timetabled train legs, keyed by ``(boarding stop, alighting stop)``."""
    index: dict[tuple[str, str], list[Leg]] = {}
    for journey in journeys:
        for leg in journey.legs:
            board, alight = leg.departure_point.naptan_id, leg.arrival_point.naptan_id
            if is_train(leg) and board and alight:
                index.setdefault((board, alight), []).append(leg)
    return index


def _live_train(
    leg: Leg, board: str, alight: str, ready_at: datetime, ctx: JourneyContext
) -> Arrival | None:
    lines = leg_lines(leg)
    margin = timedelta(seconds=ctx.profile.safety_margin_s)
    for arrival in sorted(ctx.arrivals_by_stop.get(board, ()), key=lambda a: a.expected_arrival):
        if arrival.line_id not in lines or arrival.destination_naptan_id is None:
            continue
        if arrival.expected_arrival - ready_at < margin:
            continue
        routes = ctx.routes_by_line.get(arrival.line_id, ())
        if calls_at(routes, board, alight, arrival.destination_naptan_id):
            return arrival
    return None


def _timetabled_train(
    leg: Leg, board: str, alight: str, ready_at: datetime, ctx: JourneyContext
) -> Leg | None:
    lines = leg_lines(leg)
    margin = timedelta(seconds=ctx.profile.safety_margin_s)
    candidates = [
        t
        for t in ctx.timetable.get((board, alight), ())
        if (not lines or leg_lines(t) & lines) and t.departure_time - ready_at >= margin
    ]
    return min(candidates, key=lambda t: t.departure_time, default=None)


def train_leg(leg: Leg, ready_at: datetime, ctx: JourneyContext) -> TrainLeg | None:
    """Return the train to catch for a TfL train leg, when on the platform at ``ready_at``."""
    board, alight = leg.departure_point.naptan_id, leg.arrival_point.naptan_id
    if board is None or alight is None:
        return None
    ride = leg.arrival_time - leg.departure_time
    live = _live_train(leg, board, alight, ready_at, ctx)
    if live is not None:
        departs = live.expected_arrival
        line_id, line_name = live.line_id, live.line_name
        destination, platform = live.destination_name, live.platform_name
        source: Literal["live", "timetable"] = "live"
    else:
        timetabled = _timetabled_train(leg, board, alight, ready_at, ctx)
        if timetabled is None:
            return None
        departs = timetabled.departure_time
        ride = timetabled.arrival_time - timetabled.departure_time
        option = next((o for o in timetabled.route_options if o.line is not None), None)
        line_id = option.line.id if option and option.line else timetabled.mode.id
        line_name = option.line.name if option and option.line else timetabled.mode.name
        destination = option.directions[0] if option and option.directions else None
        platform = timetabled.departure_point.platform_name
        source = "timetable"
    wait = (departs - ready_at).total_seconds()
    return TrainLeg(
        line_id=line_id,
        line_name=line_name,
        from_stop_id=board,
        from_name=leg.departure_point.name,
        to_stop_id=alight,
        to_name=leg.arrival_point.name,
        destination_name=destination,
        platform_name=platform,
        departure_time=departs,
        arrival_time=departs + ride,
        wait_seconds=wait,
        margin_seconds=wait - ctx.profile.safety_margin_s,
        source=source,
    )


# --------------------------------------------------------------------------- whole journeys


def retime(journey: Journey, ctx: JourneyContext) -> JourneyOption | MissingTrain | None:
    """Time one TfL journey for this walker, leaving now.

    Returns :class:`MissingTrain` for the first train leg with no live train or timetabled
    departure late enough, and ``None`` when a train leg has no stop ids to match on.
    """
    t = ctx.now
    legs: list[JourneyLeg] = []
    margins: list[float] = []
    previous: Leg | None = None
    for leg in journey.legs:
        if not is_train(leg):
            walk = walk_leg(leg, ctx)
            legs.append(walk)
            t += timedelta(seconds=walk.seconds)
        else:
            if previous is None:  # starts at a station: still need to reach the platform
                stop = leg.departure_point.naptan_id or ""
                entry = ctx.entry_buffers.get(stop, ctx.default_entry_buffer_s)
                name = leg.departure_point.name
                legs.append(WalkLeg(name, name, 0.0, 0.0, entry, entry))
                t += timedelta(seconds=entry)
            elif is_train(previous):
                stop = previous.arrival_point.naptan_id or ""
                seconds = ctx.change_seconds.get(stop, 0.0)
                legs.append(ChangeLeg(stop, previous.arrival_point.name, seconds))
                t += timedelta(seconds=seconds)
            board, alight = leg.departure_point.naptan_id, leg.arrival_point.naptan_id
            if board is None or alight is None:
                return None
            train = train_leg(leg, t, ctx)
            if train is None:
                return MissingTrain(board, alight, t)
            legs.append(train)
            margins.append(train.margin_seconds)
            t = train.arrival_time
        previous = leg
    first_margin = margins[0] if margins else 0.0
    return JourneyOption(
        leave_by=ctx.now + timedelta(seconds=first_margin),
        arrival_time=t,
        legs=tuple(legs),
        margin_seconds=min(margins) if margins else None,
    )


def _signature(option: JourneyOption) -> tuple[object, ...]:
    trains = tuple(
        (leg.line_id, leg.from_stop_id, leg.departure_time)
        for leg in option.legs
        if isinstance(leg, TrainLeg)
    )
    return trains or ("walk",)


def build_journey_options(
    journeys: Sequence[Journey],
    *,
    profile: WalkerProfile,
    tfl_setting: WalkingSpeed,
    now: datetime,
    arrivals_by_stop: Mapping[str, Sequence[Arrival]],
    routes_by_line: Mapping[str, Sequence[OrderedRoute]],
    entry_buffers: Mapping[str, float],
    change_times: Mapping[str, float],
    default_entry_buffer_s: float,
    extra_timetable: Sequence[Journey] = (),
) -> JourneyBuild:
    """Re-time TfL's journeys for this walker; earliest arrival first, duplicates dropped.

    Args:
        journeys: TfL's plans, made with ``walking_speed=tfl_setting``.
        profile: The walker's speed and risk setting.
        tfl_setting: The TfL walking-speed setting the plans were made with.
        now: The time the walker sets off.
        arrivals_by_stop: Live arrivals at each boarding stop.
        routes_by_line: Every route of each line, in both directions.
        entry_buffers: Street-to-platform seconds at the walker's pace, by stop id; these
            replace TfL's station time on walks to or from that stop.
        change_times: Platform-to-platform seconds at the walker's pace, by the stop where
            they get off; these replace TfL's change time there.
        default_entry_buffer_s: Street-to-platform seconds for a journey that starts at a
            station, where TfL has no walk leg to learn from.
        extra_timetable: More TfL plans whose train legs add timetabled departures, e.g.
            fetched for a previous build's ``missing`` hops. They are not offered as routes.

    """
    ratio = TFL_PACE_KMH[tfl_setting] / profile.walking_speed_kmh
    changes = {stop: s * ratio for stop, s in tfl_change_seconds(journeys).items()}
    changes.update(change_times)
    ctx = JourneyContext(
        profile=profile,
        tfl_setting=tfl_setting,
        now=now,
        arrivals_by_stop=arrivals_by_stop,
        routes_by_line=routes_by_line,
        timetable=timetable_index([*journeys, *extra_timetable]),
        change_seconds=changes,
        entry_buffers=entry_buffers,
        default_entry_buffer_s=default_entry_buffer_s,
    )
    results = [retime(j, ctx) for j in journeys]
    options = [r for r in results if isinstance(r, JourneyOption)]
    missing = list(dict.fromkeys(r for r in results if isinstance(r, MissingTrain)))
    options.sort(key=lambda o: (o.arrival_time, -o.leave_by.timestamp()))
    seen: set[tuple[object, ...]] = set()
    unique = []
    for option in options:
        key = _signature(option)
        if key not in seen:
            seen.add(key)
            unique.append(option)
    return JourneyBuild(unique, missing)

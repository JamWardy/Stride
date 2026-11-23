"""Planners that fetch live TfL data and turn it into walk options."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from tfl import (
    Arrival,
    AsyncTflClient,
    Direction,
    Journey,
    NearbyStop,
    OrderedRoute,
    TflClient,
    TflNotFoundError,
)

from .journeys import (
    DEFAULT_MODES,
    JourneyBuild,
    JourneyOption,
    MissingTrain,
    build_journey_options,
    is_train,
    leg_lines,
)
from .options import ReachableStation, WalkOption, build_options
from .walking import StraightLineWalk, WalkerProfile, WalkEstimator, nearest_tfl_setting

DEFAULT_ENTRY_BUFFER_S = 120.0
#: How many times a journey planner goes back to TfL for timetabled trains beyond the live
#: horizon; each round can fill one more train leg of a journey.
MAX_TIMETABLE_ROUNDS = 3


class _BasePlanner:
    """Settings and pure steps shared by :class:`WalkPlanner` and :class:`AsyncWalkPlanner`."""

    def __init__(
        self,
        profile: WalkerProfile,
        walk_estimator: WalkEstimator | None,
        entry_buffer_s: float,
        entry_buffers: Mapping[str, float] | None,
    ) -> None:
        self.profile = profile
        self.walk_estimator: WalkEstimator = walk_estimator or StraightLineWalk()
        self.entry_buffer_s = entry_buffer_s
        self.entry_buffers = dict(entry_buffers or {})

    def _search_radius_m(self, max_walk_minutes: float) -> int:
        """Straight-line radius the walker could cover in ``max_walk_minutes``.

        Real walking distance is never shorter than the straight line, so this finds every
        station in range whatever the estimator; stations too far once streets are
        accounted for are dropped by :meth:`_reachable`.
        """
        if max_walk_minutes <= 0:
            raise ValueError("max_walk_minutes must be positive")
        return math.ceil(self.profile.speed_m_s * max_walk_minutes * 60)

    def _reachable(
        self, lat: float, lon: float, stops: Sequence[NearbyStop], max_walk_minutes: float
    ) -> list[ReachableStation]:
        stations = []
        for stop in stops:
            walk_s = self.walk_estimator.walk_seconds(
                lat, lon, stop.lat, stop.lon, self.profile.speed_m_s
            )
            if walk_s <= max_walk_minutes * 60:
                buffer_s = self.entry_buffers.get(stop.id, self.entry_buffer_s)
                stations.append(ReachableStation(stop.id, stop.name, walk_s, buffer_s))
        return stations


class WalkPlanner(_BasePlanner):
    """Finds the trains a walker can catch from where they are standing.

    Example:
        >>> planner = WalkPlanner(client, WalkerProfile(walking_speed_kmh=5.5))
        >>> for opt in planner.options_from(lat=51.515, lon=-0.141, max_walk_minutes=12):
        ...     print(opt.station_name, opt.line_name, opt.walk_minutes, opt.wait_minutes)

    Args:
        client: The TfL client used to look up stations and arrivals.
        profile: Walking speed and risk setting.
        walk_estimator: How walking time is estimated. Defaults to
            :class:`~tfl_walk.StraightLineWalk` (haversine * 1.3 detour factor).
        entry_buffer_s: Seconds from the street to the platform, for any station not in
            ``entry_buffers``.
        entry_buffers: Per-station overrides of ``entry_buffer_s``, keyed by station id.

    """

    def __init__(
        self,
        client: TflClient,
        profile: WalkerProfile,
        *,
        walk_estimator: WalkEstimator | None = None,
        entry_buffer_s: float = DEFAULT_ENTRY_BUFFER_S,
        entry_buffers: Mapping[str, float] | None = None,
    ) -> None:
        super().__init__(profile, walk_estimator, entry_buffer_s, entry_buffers)
        self._client = client

    def options_from(self, lat: float, lon: float, max_walk_minutes: float) -> list[WalkOption]:
        """Return the catchable trains at stations within ``max_walk_minutes`` on foot.

        Returns:
            The earliest catchable train per station, line and direction, soonest first.
            Empty when nothing in range can be caught.

        Raises:
            ValueError: If ``max_walk_minutes`` is not positive.
            tfl.TflError: If a TfL request fails.

        """
        radius = self._search_radius_m(max_walk_minutes)
        stops = self._client.stops.nearby(lat, lon, radius_m=radius)
        stations = self._reachable(lat, lon, stops, max_walk_minutes)
        arrivals = {s.id: self._client.stops.arrivals(s.id) for s in stations}
        return build_options(stations, arrivals, self.profile.safety_margin_s)


class AsyncWalkPlanner(_BasePlanner):
    """Async version of :class:`WalkPlanner`; fetches each station's arrivals concurrently.

    Args:
        client: The async TfL client used to look up stations and arrivals.
        profile: Walking speed and risk setting.
        walk_estimator: How walking time is estimated. Defaults to
            :class:`~tfl_walk.StraightLineWalk` (haversine * 1.3 detour factor).
        entry_buffer_s: Seconds from the street to the platform, for any station not in
            ``entry_buffers``.
        entry_buffers: Per-station overrides of ``entry_buffer_s``, keyed by station id.

    """

    def __init__(
        self,
        client: AsyncTflClient,
        profile: WalkerProfile,
        *,
        walk_estimator: WalkEstimator | None = None,
        entry_buffer_s: float = DEFAULT_ENTRY_BUFFER_S,
        entry_buffers: Mapping[str, float] | None = None,
    ) -> None:
        super().__init__(profile, walk_estimator, entry_buffer_s, entry_buffers)
        self._client = client

    async def options_from(
        self, lat: float, lon: float, max_walk_minutes: float
    ) -> list[WalkOption]:
        """Return the catchable trains at stations within ``max_walk_minutes`` on foot.

        Returns:
            The earliest catchable train per station, line and direction, soonest first.
            Empty when nothing in range can be caught.

        Raises:
            ValueError: If ``max_walk_minutes`` is not positive.
            tfl.TflError: If a TfL request fails.

        """
        radius = self._search_radius_m(max_walk_minutes)
        stops = await self._client.stops.nearby(lat, lon, radius_m=radius)
        stations = self._reachable(lat, lon, stops, max_walk_minutes)
        results = await asyncio.gather(*(self._client.stops.arrivals(s.id) for s in stations))
        arrivals = {s.id: r for s, r in zip(stations, results, strict=True)}
        return build_options(stations, arrivals, self.profile.safety_margin_s)


# --------------------------------------------------------------------------- journeys


class _BaseJourneyPlanner:
    """Settings and pure steps shared by :class:`JourneyPlanner` and its async twin."""

    def __init__(
        self,
        profile: WalkerProfile,
        modes: Sequence[str],
        entry_buffers: Mapping[str, float] | None,
        change_times: Mapping[str, float] | None,
        default_entry_buffer_s: float,
    ) -> None:
        self.profile = profile
        self.modes = tuple(modes)
        self.entry_buffers = dict(entry_buffers or {})
        self.change_times = dict(change_times or {})
        self.default_entry_buffer_s = default_entry_buffer_s
        self.tfl_setting = nearest_tfl_setting(profile.walking_speed_kmh)

    @staticmethod
    def _boarding_stops_and_lines(journeys: Sequence[Journey]) -> tuple[list[str], list[str]]:
        legs = [leg for j in journeys for leg in j.legs if is_train(leg)]
        stops = {leg.departure_point.naptan_id for leg in legs} - {None}
        lines = {line for leg in legs for line in leg_lines(leg)}
        return sorted(s for s in stops if s), sorted(lines)

    def _build(
        self,
        journeys: Sequence[Journey],
        now: datetime,
        arrivals: Mapping[str, Sequence[Arrival]],
        routes: Mapping[str, Sequence[OrderedRoute]],
        extra_timetable: Sequence[Journey],
    ) -> JourneyBuild:
        return build_journey_options(
            journeys,
            profile=self.profile,
            tfl_setting=self.tfl_setting,
            now=now,
            arrivals_by_stop=arrivals,
            routes_by_line=routes,
            entry_buffers=self.entry_buffers,
            change_times=self.change_times,
            default_entry_buffer_s=self.default_entry_buffer_s,
            extra_timetable=extra_timetable,
        )


class JourneyPlanner(_BaseJourneyPlanner):
    """Door-to-door journeys timed at the walker's own pace, against live trains.

    Example:
        >>> planner = JourneyPlanner(client, WalkerProfile(walking_speed_kmh=6))
        >>> for option in planner.journeys("51.5226,-0.1571", "940GZZLUBNK"):
        ...     print(option.leave_by, option.arrival_time, option.margin_seconds)

    Args:
        client: The TfL client used for journey plans, arrivals and route sequences.
        profile: Walking speed and risk setting.
        modes: TfL modes to travel by; include ``"walking"``.
        entry_buffers: Street-to-platform seconds at this walker's pace, by stop id,
            replacing TfL's station time for walks to or from that stop.
        change_times: Platform-to-platform seconds at this walker's pace, by the stop where
            they get off, replacing TfL's change time there.
        default_entry_buffer_s: Street-to-platform seconds for a journey that starts at a
            station (TfL has no walk leg to learn from there).

    """

    def __init__(
        self,
        client: TflClient,
        profile: WalkerProfile,
        *,
        modes: Sequence[str] = DEFAULT_MODES,
        entry_buffers: Mapping[str, float] | None = None,
        change_times: Mapping[str, float] | None = None,
        default_entry_buffer_s: float = DEFAULT_ENTRY_BUFFER_S,
    ) -> None:
        super().__init__(profile, modes, entry_buffers, change_times, default_entry_buffer_s)
        self._client = client

    def journeys(self, from_: str, to: str) -> list[JourneyOption]:
        """Ways to get from ``from_`` to ``to`` leaving now, earliest arrival first.

        Args:
            from_: Anything TfL's journey planner accepts: ``"lat,lon"``, a stop id, a
                postcode, or a place name.
            to: Where to go, in any of the same forms.

        Raises:
            tfl.TflAmbiguousLocationError: If ``from_`` or ``to`` matches several places.
            tfl.TflError: If a TfL request fails.

        """
        now = datetime.now(UTC)
        journeys = self._client.journeys.plan(
            from_, to, modes=self.modes, walking_speed=self.tfl_setting
        )
        stops, lines = self._boarding_stops_and_lines(journeys)
        arrivals = {s: self._client.stops.arrivals(s) for s in stops}
        routes = {
            line: [
                r
                for d in ("inbound", "outbound")
                for r in self._client.lines.route_sequence(line, d).routes
            ]
            for line in lines
        }
        extra: list[Journey] = []
        build = self._build(journeys, now, arrivals, routes, extra)
        for _ in range(MAX_TIMETABLE_ROUNDS):
            if not build.missing:
                break
            for m in build.missing:
                try:
                    extra.extend(
                        self._client.journeys.plan(
                            m.board,
                            m.alight,
                            depart_at=m.ready_at,
                            modes=self.modes,
                            walking_speed=self.tfl_setting,
                        )
                    )
                except TflNotFoundError:  # no service on that hop: its journeys are dropped
                    continue
            build = self._build(journeys, now, arrivals, routes, extra)
        return build.options


class AsyncJourneyPlanner(_BaseJourneyPlanner):
    """Async version of :class:`JourneyPlanner`; fetches arrivals and routes concurrently."""

    def __init__(
        self,
        client: AsyncTflClient,
        profile: WalkerProfile,
        *,
        modes: Sequence[str] = DEFAULT_MODES,
        entry_buffers: Mapping[str, float] | None = None,
        change_times: Mapping[str, float] | None = None,
        default_entry_buffer_s: float = DEFAULT_ENTRY_BUFFER_S,
    ) -> None:
        super().__init__(profile, modes, entry_buffers, change_times, default_entry_buffer_s)
        self._client = client

    async def _hop(self, m: MissingTrain) -> list[Journey]:
        try:
            return await self._client.journeys.plan(
                m.board,
                m.alight,
                depart_at=m.ready_at,
                modes=self.modes,
                walking_speed=self.tfl_setting,
            )
        except TflNotFoundError:  # no service on that hop: its journeys are dropped
            return []

    async def journeys(self, from_: str, to: str) -> list[JourneyOption]:
        """Ways to get from ``from_`` to ``to`` leaving now. See :meth:`JourneyPlanner.journeys`."""
        now = datetime.now(UTC)
        journeys = await self._client.journeys.plan(
            from_, to, modes=self.modes, walking_speed=self.tfl_setting
        )
        stops, lines = self._boarding_stops_and_lines(journeys)
        directions: tuple[Direction, ...] = ("inbound", "outbound")
        wanted = [(line, d) for line in lines for d in directions]
        arrival_lists, sequences = await asyncio.gather(
            asyncio.gather(*(self._client.stops.arrivals(s) for s in stops)),
            asyncio.gather(*(self._client.lines.route_sequence(ln, d) for ln, d in wanted)),
        )
        arrivals = dict(zip(stops, arrival_lists, strict=True))
        routes: dict[str, list[OrderedRoute]] = {line: [] for line in lines}
        for (line, _), seq in zip(wanted, sequences, strict=True):
            routes[line].extend(seq.routes)
        extra: list[Journey] = []
        build = self._build(journeys, now, arrivals, routes, extra)
        for _ in range(MAX_TIMETABLE_ROUNDS):
            if not build.missing:
                break
            hops = await asyncio.gather(*(self._hop(m) for m in build.missing))
            extra.extend(j for hop in hops for j in hop)
            build = self._build(journeys, now, arrivals, routes, extra)
        return build.options

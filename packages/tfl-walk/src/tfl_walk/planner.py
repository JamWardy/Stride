"""Planners that fetch live TfL data and turn it into walk options."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence

from tfl import AsyncTflClient, NearbyStop, TflClient

from .options import ReachableStation, WalkOption, build_options
from .walking import StraightLineWalk, WalkerProfile, WalkEstimator

DEFAULT_ENTRY_BUFFER_S = 120.0


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

"""Who is walking and how long their walk takes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from tfl import WalkingSpeed

#: How much slack a walker wants between reaching the platform and the train arriving.
Risk = Literal["low", "medium", "high"]

#: Safety margin in seconds for each :data:`Risk` setting.
SAFETY_MARGIN_S: dict[Risk, float] = {"low": 90.0, "medium": 45.0, "high": 0.0}

#: The pace TfL's journey planner assumes for each ``walking_speed`` setting, in km/h, along
#: its walking routes. Measured on 2026-11-23 by fitting 41 walk-only journeys in central
#: London (duration against ``Leg.distance_m``); each fit is good to about ±1.5 min per walk,
#: mostly because TfL reports whole minutes.
TFL_PACE_KMH: dict[WalkingSpeed, float] = {"slow": 2.7, "average": 3.8, "fast": 4.6}


def nearest_tfl_setting(walking_speed_kmh: float) -> WalkingSpeed:
    """Return the TfL ``walking_speed`` setting whose pace is closest to ``walking_speed_kmh``."""
    return min(TFL_PACE_KMH, key=lambda s: abs(TFL_PACE_KMH[s] - walking_speed_kmh))


#: Mean Earth radius in metres.
EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class WalkerProfile:
    """How fast someone walks and how much risk they accept.

    The profile is plain data, so any pace source (e.g. a future Strava import) only has to
    produce a ``walking_speed_kmh``.
    """

    walking_speed_kmh: float
    risk: Risk = "medium"

    def __post_init__(self) -> None:
        if self.walking_speed_kmh <= 0:
            raise ValueError("walking_speed_kmh must be positive")
        if self.risk not in SAFETY_MARGIN_S:
            raise ValueError(f"risk must be one of {sorted(SAFETY_MARGIN_S)}")

    @property
    def speed_m_s(self) -> float:
        """Walking speed in metres per second."""
        return self.walking_speed_kmh / 3.6

    @property
    def safety_margin_s(self) -> float:
        """Seconds of slack required by this profile's ``risk`` setting."""
        return SAFETY_MARGIN_S[self.risk]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class WalkEstimator(Protocol):
    """Estimates walking time between two points.

    This is the extension point for real street routing (e.g. OSRM or OpenRouteService):
    implement ``walk_seconds`` and pass the estimator to the planner.
    """

    def walk_seconds(
        self, from_lat: float, from_lon: float, to_lat: float, to_lon: float, speed_m_s: float
    ) -> float:
        """Return the estimated walking time in seconds."""
        ...


@dataclass(frozen=True)
class StraightLineWalk:
    """Haversine distance stretched by ``detour_factor`` to allow for streets, at walking speed."""

    detour_factor: float = 1.3

    def __post_init__(self) -> None:
        if self.detour_factor < 1:
            raise ValueError("detour_factor must be at least 1")

    def walk_seconds(
        self, from_lat: float, from_lon: float, to_lat: float, to_lon: float, speed_m_s: float
    ) -> float:
        """Return ``haversine * detour_factor / speed``."""
        return haversine_m(from_lat, from_lon, to_lat, to_lon) * self.detour_factor / speed_m_s

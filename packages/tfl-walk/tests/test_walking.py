from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tfl import Arrival
from tfl_walk import (
    ReachableStation,
    StraightLineWalk,
    WalkerProfile,
    best_per_line_direction,
    build_options,
    catchable_options,
    haversine_m,
)

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)


def arrival(
    seconds: int,
    line: str = "victoria",
    direction: str | None = "outbound",
    n: int = 0,
    destination_id: str | None = None,
) -> Arrival:
    return Arrival(
        id=f"{line}-{direction}-{seconds}-{n}",
        line_id=line,
        line_name=line.title(),
        expected_arrival=NOW + timedelta(seconds=seconds),
        time_to_station=seconds,
        direction=direction,
        destination_naptan_id=destination_id,
    )


def station(walk: float = 300, buffer: float = 120, id_: str = "OXC") -> ReachableStation:
    return ReachableStation(id=id_, name=id_, walk_seconds=walk, entry_buffer_seconds=buffer)


# ------------------------------------------------------------------ walking maths


def test_haversine_matches_tfl_distance() -> None:
    # TfL's own distance from (51.515, -0.141) to Bond Street in the recorded fixture.
    assert haversine_m(51.515, -0.141, 51.514304, -0.149723) == pytest.approx(609.08, abs=1)


def test_straight_line_walk_applies_detour_and_speed() -> None:
    profile = WalkerProfile(walking_speed_kmh=3.6)  # 1 m/s
    d = haversine_m(51.515, -0.141, 51.514304, -0.149723)
    walk = StraightLineWalk(detour_factor=1.5).walk_seconds(
        51.515, -0.141, 51.514304, -0.149723, profile.speed_m_s
    )
    assert walk == pytest.approx(d * 1.5)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"walking_speed_kmh": 0}, "walking_speed_kmh"),
        ({"walking_speed_kmh": 5, "risk": "extreme"}, "risk"),
    ],
)
def test_profile_validation(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        WalkerProfile(**kwargs)  # type: ignore[arg-type]


# ------------------------------------------------------------------ catchability


@pytest.mark.parametrize(("risk", "margin"), [("low", 90), ("medium", 45), ("high", 0)])
def test_catchable_exactly_at_risk_margin(risk: str, margin: int) -> None:
    safety = WalkerProfile(5, risk=risk).safety_margin_s  # type: ignore[arg-type]
    assert safety == margin
    needed = 300 + 120 + margin  # walk + buffer + safety margin
    [opt] = catchable_options(station(), [arrival(needed)], safety)
    assert opt.wait_seconds == margin  # all the slack is the safety margin
    assert opt.margin_seconds == 0
    assert opt.can_make_it
    assert catchable_options(station(), [arrival(needed - 1)], safety) == []


def test_trains_terminating_at_the_station_are_skipped() -> None:
    # Seen live at Bank DLR: trains to "Bank DLR Station" arriving at Bank DLR.
    arrivals = [
        arrival(900, destination_id="OXC"),  # terminates here
        arrival(900, destination_id="BRX", n=1),
        arrival(900, n=2),  # no destination given: kept
    ]
    options = catchable_options(station(id_="OXC"), arrivals, 0)
    assert len(options) == 2


def test_option_times() -> None:
    [opt] = catchable_options(station(walk=330), [arrival(1000)], 45)
    assert opt.walk_minutes == pytest.approx(5.5)
    assert opt.wait_seconds == 1000 - 330 - 120
    assert opt.wait_minutes == pytest.approx(550 / 60)
    assert opt.margin_seconds == 550 - 45
    assert opt.departure_time == NOW + timedelta(seconds=1000)


# ------------------------------------------------------------------ sorting and dedupe


def test_keeps_earliest_per_station_line_direction_sorted_by_departure() -> None:
    arrivals = [
        arrival(900, "victoria", "outbound"),
        arrival(600, "victoria", "outbound"),  # earliest outbound Victoria: kept
        arrival(700, "victoria", "inbound"),
        arrival(800, "central", "outbound"),
    ]
    options = best_per_line_direction(catchable_options(station(), arrivals, 0))
    assert [(o.line_id, o.direction, o.wait_seconds + 420) for o in options] == [
        ("victoria", "outbound", 600),
        ("victoria", "inbound", 700),
        ("central", "outbound", 800),
    ]


def test_same_line_at_different_stations_kept_separately() -> None:
    near, far = station(walk=100, id_="A"), station(walk=400, id_="B")
    options = build_options([near, far], {"A": [arrival(900)], "B": [arrival(900, n=1)]}, 0)
    assert [o.station_id for o in options] == ["A", "B"]  # same departure: shorter walk first


def test_nothing_catchable_returns_empty() -> None:
    assert build_options([station()], {"OXC": [arrival(60)]}, 45) == []

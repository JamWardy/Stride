"""Journey re-timing with hand-built data: no HTTP."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from tfl import Arrival, Journey, OrderedRoute
from tfl_walk import (
    ChangeLeg,
    JourneyOption,
    MissingTrain,
    TrainLeg,
    WalkerProfile,
    WalkLeg,
    build_journey_options,
    calls_at,
    nearest_tfl_setting,
)

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
A, B, C, D, E = "STOP_A", "STOP_B", "STOP_C", "STOP_D", "STOP_E"
# TfL "average" is 3.8 km/h; a 7.6 km/h walker takes half TfL's time for everything on foot.
FAST = WalkerProfile(walking_speed_kmh=7.6, risk="high")  # no safety margin
ROUTES = {
    "red": [
        OrderedRoute(name="A-D", stop_ids=[A, B, C, D]),
        OrderedRoute(name="D-A", stop_ids=[D, C, B, A]),
    ],
    "blue": [OrderedRoute(name="C-E", stop_ids=[C, E])],
}


def at(minutes: float) -> datetime:
    return NOW + timedelta(minutes=minutes)


def place(stop: str | None, name: str | None = None) -> dict[str, Any]:
    return {"commonName": name or stop or "street", "lat": 51.5, "lon": -0.1, "naptanId": stop}


def walk(
    frm: str | None, to: str | None, start: float, minutes: int, metres: float
) -> dict[str, Any]:
    return {
        "duration": minutes,
        "distance": metres,
        "instruction": {"summary": "Walk"},
        "mode": {"id": "walking", "name": "walking"},
        "departureTime": at(start).isoformat(),
        "arrivalTime": at(start + minutes).isoformat(),
        "departurePoint": place(frm),
        "arrivalPoint": place(to),
    }


def train(line: str, frm: str, to: str, start: float, minutes: int) -> dict[str, Any]:
    return {
        "duration": minutes,
        "instruction": {"summary": f"{line} line"},
        "mode": {"id": "tube", "name": "tube"},
        "departureTime": at(start).isoformat(),
        "arrivalTime": at(start + minutes).isoformat(),
        "departurePoint": place(frm),
        "arrivalPoint": place(to),
        "routeOptions": [
            {
                "name": line,
                "directions": [f"towards {to}"],
                "lineIdentifier": {"id": line, "name": line.title()},
            }
        ],
    }


def journey(*legs: dict[str, Any]) -> Journey:
    return Journey.model_validate(
        {
            "startDateTime": legs[0]["departureTime"],
            "arrivalDateTime": legs[-1]["arrivalTime"],
            "duration": 0,
            "legs": list(legs),
        }
    )


def live(line: str, minutes: float, terminus: str, n: int = 0) -> Arrival:
    return Arrival(
        id=f"{line}-{minutes}-{n}",
        line_id=line,
        line_name=line.title(),
        expected_arrival=at(minutes),
        time_to_station=int(minutes * 60),
        destination_naptan_id=terminus,
        destination_name=terminus,
        platform_name="Platform 1",
    )


def build(
    journeys: Sequence[Journey],
    arrivals: dict[str, list[Arrival]] | None = None,
    profile: WalkerProfile = FAST,
    **kwargs: Any,
) -> tuple[list[JourneyOption], list[MissingTrain]]:
    result = build_journey_options(
        journeys,
        profile=profile,
        tfl_setting="average",
        now=NOW,
        arrivals_by_stop=arrivals or {},
        routes_by_line=ROUTES,
        entry_buffers=kwargs.pop("entry_buffers", {}),
        change_times=kwargs.pop("change_times", {}),
        default_entry_buffer_s=kwargs.pop("default_entry_buffer_s", 120),
        **kwargs,
    )
    return result.options, result.missing


def trains(option: JourneyOption) -> list[TrainLeg]:
    return [leg for leg in option.legs if isinstance(leg, TrainLeg)]


# ------------------------------------------------------------------ matching trains to legs


@pytest.mark.parametrize(
    ("board", "alight", "terminus", "expected"),
    [
        (A, C, D, True),  # runs through C to D
        (A, C, C, True),  # terminates where we get off
        (A, C, B, False),  # terminates before our stop
        (C, A, D, False),  # wrong direction
        (A, E, D, False),  # E is on another line
    ],
)
def test_calls_at(board: str, alight: str, terminus: str, expected: bool) -> None:
    assert calls_at(ROUTES["red"], board, alight, terminus) is expected


def test_nearest_tfl_setting() -> None:
    assert [nearest_tfl_setting(k) for k in (2.0, 3.2, 4.0, 6.5)] == [
        "slow",
        "slow",
        "average",
        "fast",
    ]


# ------------------------------------------------------------------ walking


def test_walk_is_street_at_walker_speed_plus_scaled_station_time() -> None:
    # TfL: 380 m at 3.8 km/h = 6 min of street, so 2 of its 8 minutes are station time.
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5))
    [option], _ = build([j], {A: [live("red", 30, D)]})
    w = option.legs[0]
    assert isinstance(w, WalkLeg)
    assert w.street_seconds == pytest.approx(180)  # 380 m at 7.6 km/h
    assert w.station_seconds == pytest.approx(60)  # TfL's 120 s, halved
    assert w.seconds == pytest.approx(240)


def test_entry_buffer_override_replaces_tfl_station_time() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5))
    [option], _ = build([j], {A: [live("red", 30, D)]}, entry_buffers={A: 200})
    w = option.legs[0]
    assert isinstance(w, WalkLeg)
    assert w.station_seconds == 200


def test_street_only_walk_has_no_station_time() -> None:
    [option], _ = build([journey(walk(None, None, 0, 7, 380))])
    [w] = option.legs
    assert isinstance(w, WalkLeg)
    assert w.station_seconds == 0
    assert w.seconds == pytest.approx(180)
    assert option.margin_seconds is None
    assert option.leave_by == NOW
    assert option.arrival_time == NOW + timedelta(seconds=180)


# ------------------------------------------------------------------ catching trains


def test_catches_first_live_train_that_calls_at_the_stop() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5))  # on the platform at 4 min
    arrivals = {
        A: [
            live("red", 3, D),  # gone before we get there
            live("red", 5, B, n=1),  # terminates before C
            live("blue", 5, E),  # another line
            live("red", 6, D, n=2),  # this one
            live("red", 9, D, n=3),
        ]
    }
    [option], _ = build([j], arrivals)
    [t] = trains(option)
    assert t.source == "live"
    assert t.departure_time == at(6)
    assert t.arrival_time == at(11)  # TfL's 5-minute ride
    assert t.wait_seconds == pytest.approx(120)
    assert option.leave_by == NOW + timedelta(seconds=120)
    assert option.arrival_time == at(11)


@pytest.mark.parametrize(("risk", "expected_departure"), [("high", 5), ("medium", 5), ("low", 6)])
def test_risk_margin_decides_the_train(risk: str, expected_departure: int) -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5))  # ready at 4 min
    arrivals = {A: [live("red", 5, D), live("red", 6, D, n=1)]}  # 60 s and 120 s after ready
    profile = WalkerProfile(walking_speed_kmh=7.6, risk=risk)  # type: ignore[arg-type]
    [option], _ = build([j], arrivals, profile=profile)
    assert trains(option)[0].departure_time == at(expected_departure)


def test_change_uses_tfls_smallest_gap_scaled() -> None:
    # TfL: change at C takes 4 min in one journey and 6 in the other; we use 4, halved.
    j1 = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5), train("blue", C, E, 19, 3))
    j2 = journey(walk(None, A, 2, 8, 380), train("red", A, C, 12, 5), train("blue", C, E, 23, 3))
    arrivals = {A: [live("red", 6, D)], C: [live("blue", 12, E), live("blue", 14, E, n=1)]}
    [option], _ = build([j1, j2], arrivals)  # both re-time to the same trains: deduplicated
    change = next(leg for leg in option.legs if isinstance(leg, ChangeLeg))
    assert change.seconds == pytest.approx(120)
    # Off the red train at 11, on the platform at 13: the 12:00 blue train is gone.
    assert [t.departure_time for t in trains(option)] == [at(6), at(14)]
    assert option.margin_seconds == pytest.approx(60)  # the tighter of 120 s and 60 s
    assert option.leave_by == NOW + timedelta(seconds=120)  # set by the first train


def test_change_time_override() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5), train("blue", C, E, 19, 3))
    arrivals = {A: [live("red", 6, D)], C: [live("blue", 12, E)]}
    [option], _ = build([j], arrivals, change_times={C: 30})
    assert trains(option)[1].departure_time == at(12)


def test_falls_back_to_timetable_beyond_live_horizon() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 5))
    [option], missing = build([j], {A: [live("red", 2, D)]})  # live list ends too early
    [t] = trains(option)
    assert (t.source, t.departure_time, t.arrival_time) == ("timetable", at(10), at(15))
    assert missing == []


def test_reports_missing_train_when_timetable_is_too_early_too() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 3, 5))  # TfL's train left at 3
    options, missing = build([j], {A: []})
    assert options == []
    assert missing == [MissingTrain(A, C, NOW + timedelta(seconds=240))]


def test_extra_timetable_fills_a_missing_train() -> None:
    j = journey(walk(None, A, 0, 8, 380), train("red", A, C, 3, 5))
    later = journey(train("red", A, C, 7, 5))
    [option], missing = build([j], {A: []}, extra_timetable=[later])
    assert trains(option)[0].departure_time == at(7)
    assert missing == []


def test_journey_starting_at_a_station_uses_default_entry_buffer() -> None:
    j = journey(train("red", A, C, 10, 5))
    [option], _ = build(
        [j], {A: [live("red", 1, D), live("red", 3, D, n=1)]}, default_entry_buffer_s=120
    )
    entry = option.legs[0]
    assert isinstance(entry, WalkLeg)
    assert entry.seconds == 120
    assert trains(option)[0].departure_time == at(3)


def test_sorted_by_arrival() -> None:
    slow = journey(walk(None, A, 0, 8, 380), train("red", A, C, 10, 20))
    quick = journey(walk(None, B, 0, 8, 380), train("red", B, C, 10, 5))
    arrivals = {A: [live("red", 6, D)], B: [live("red", 6, D)]}
    options, _ = build([slow, quick], arrivals)
    assert [trains(o)[0].from_stop_id for o in options] == [B, A]

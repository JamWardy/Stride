"""Endpoint tests with tfl-walk's planner replaced by a fake."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from speedy_api import main
from tfl import LocationOption, Place, TflAmbiguousLocationError, TflNotFoundError, TflServerError
from tfl_walk import JourneyOption, TrainLeg, WalkerProfile, WalkLeg

T = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)

OPTION = JourneyOption(
    leave_by=T,
    arrival_time=T.replace(minute=20),
    legs=(
        WalkLeg("street", "Oxford Circus", 200.0, 120.0, 60.0, 180.0),
        TrainLeg(
            line_id="victoria",
            line_name="Victoria",
            from_stop_id="940GZZLUOXC",
            from_name="Oxford Circus Underground Station",
            to_stop_id="940GZZLUVIC",
            to_name="Victoria Underground Station",
            destination_name="Brixton Underground Station",
            platform_name="Southbound - Platform 5",
            departure_time=T.replace(minute=5),
            arrival_time=T.replace(minute=12),
            wait_seconds=120.0,
            margin_seconds=75.0,
            source="live",
        ),
    ),
    margin_seconds=75.0,
)


class FakePlanner:
    """Stands in for AsyncJourneyPlanner and records how it was called."""

    calls: ClassVar[list[dict[str, Any]]] = []
    result: ClassVar[list[JourneyOption] | Exception] = [OPTION]

    def __init__(self, client: object, profile: WalkerProfile) -> None:
        self.profile = profile

    async def journeys(self, from_: str, to: str) -> list[JourneyOption]:
        FakePlanner.calls.append({"profile": self.profile, "from": from_, "to": to})
        if isinstance(FakePlanner.result, Exception):
            raise FakePlanner.result
        return FakePlanner.result


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    FakePlanner.calls = []
    FakePlanner.result = [OPTION]
    monkeypatch.setattr(main, "AsyncJourneyPlanner", FakePlanner)
    app = main.create_app(cors_origins=["http://localhost:5173"])
    app.dependency_overrides[main.get_client] = lambda: object()
    with TestClient(app) as client:
        yield client


PARAMS = {"from": "51.5226,-0.1571", "to": "Oxford Circus"}


def test_journeys_returns_legs_tagged_by_kind(http: TestClient) -> None:
    r = http.get("/journeys", params=PARAMS)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "journeys"
    [journey] = body["journeys"]
    assert journey["leave_by"] == "2026-11-23T08:00:00Z"
    assert journey["margin_seconds"] == 75.0
    walk, train = journey["legs"]
    assert walk == {
        "kind": "walk",
        "from_name": "street",
        "to_name": "Oxford Circus",
        "distance_m": 200.0,
        "street_seconds": 120.0,
        "station_seconds": 60.0,
        "seconds": 180.0,
    }
    assert train["kind"] == "train"
    assert train["line_id"] == "victoria"
    assert train["source"] == "live"
    assert train["departure_time"] == "2026-11-23T08:05:00Z"


def test_defaults_and_params_reach_the_planner(http: TestClient) -> None:
    http.get("/journeys", params=PARAMS)
    http.get("/journeys", params={**PARAMS, "speed_kmh": 6.5, "risk": "low"})
    first, second = FakePlanner.calls
    assert first == {
        "profile": WalkerProfile(walking_speed_kmh=5.5, risk="medium"),
        "from": "51.5226,-0.1571",
        "to": "Oxford Circus",
    }
    assert second["profile"] == WalkerProfile(walking_speed_kmh=6.5, risk="low")


def test_ambiguous_place_returns_candidates(http: TestClient) -> None:
    candidate = LocationOption(
        parameter_value="1000173",
        place=Place(name="Oxford Circus", lat=51.515, lon=-0.141, place_type="StopPoint"),
    )
    FakePlanner.result = TflAmbiguousLocationError("ambiguous", to_options=[candidate])
    r = http.get("/journeys", params=PARAMS)
    assert r.status_code == 200
    assert r.json() == {
        "kind": "ambiguous",
        "from_options": [],
        "to_options": [{"value": "1000173", "name": "Oxford Circus", "place_type": "StopPoint"}],
    }


def test_no_route_is_an_empty_list(http: TestClient) -> None:
    FakePlanner.result = TflNotFoundError("No journey found", status_code=404)
    r = http.get("/journeys", params=PARAMS)
    assert r.json() == {"kind": "journeys", "journeys": []}


def test_other_tfl_failures_are_502(http: TestClient) -> None:
    FakePlanner.result = TflServerError("Service Unavailable", status_code=503)
    r = http.get("/journeys", params=PARAMS)
    assert r.status_code == 502
    assert r.json() == {"detail": "TfL request failed: [503] Service Unavailable"}


@pytest.mark.parametrize(
    "params",
    [
        {"to": "Bank"},
        {"from": "51.5,-0.1"},
        {**PARAMS, "to": ""},
        {**PARAMS, "speed_kmh": 0},
        {**PARAMS, "speed_kmh": 16},
        {**PARAMS, "risk": "extreme"},
    ],
)
def test_rejects_bad_params(http: TestClient, params: dict[str, Any]) -> None:
    assert http.get("/journeys", params=params).status_code == 422
    assert FakePlanner.calls == []


def test_cors_allows_the_frontend_origin_only(http: TestClient) -> None:
    allowed = http.get("/journeys", params=PARAMS, headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = http.get("/journeys", params=PARAMS, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_app_turns_on_the_sdk_caches() -> None:
    app = main.create_app(arrivals_ttl_s=20)
    with TestClient(app):
        assert app.state.tfl.arrivals_cache.ttl == 20
        assert app.state.tfl.cache.ttl == main.CACHE_TTL_S

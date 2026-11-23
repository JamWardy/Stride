"""Endpoint tests with tfl-walk and the TfL client replaced by fakes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from speedy_api import main
from tfl import StopSummary, TflServerError
from tfl_walk import WalkerProfile, WalkOption

OPTION = WalkOption(
    station_id="940GZZLUOXC",
    station_name="Oxford Circus Underground Station",
    line_id="victoria",
    line_name="Victoria",
    direction="outbound",
    destination_name="Brixton Underground Station",
    platform_name="Southbound - Platform 5",
    departure_time=datetime(2026, 11, 23, 8, 5, tzinfo=UTC),
    walk_seconds=88.0,
    wait_seconds=200.0,
    margin_seconds=155.0,
)


class FakePlanner:
    """Stands in for AsyncWalkPlanner and records how it was called."""

    calls: ClassVar[list[dict[str, Any]]] = []
    result: ClassVar[list[WalkOption] | Exception] = [OPTION]

    def __init__(self, client: object, profile: WalkerProfile) -> None:
        self.profile = profile

    async def options_from(
        self, lat: float, lon: float, max_walk_minutes: float
    ) -> list[WalkOption]:
        FakePlanner.calls.append(
            {"profile": self.profile, "lat": lat, "lon": lon, "max_walk": max_walk_minutes}
        )
        if isinstance(FakePlanner.result, Exception):
            raise FakePlanner.result
        return FakePlanner.result


class FakeStops:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> list[StopSummary]:
        self.queries.append(query)
        return [
            StopSummary(
                id="940GZZLUOXC",
                name="Oxford Circus Underground Station",
                lat=51.515,
                lon=-0.1415,
                modes=["tube"],
            )
        ]


class FakeClient:
    def __init__(self) -> None:
        self.stops = FakeStops()


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient) -> Iterator[TestClient]:
    FakePlanner.calls = []
    FakePlanner.result = [OPTION]
    monkeypatch.setattr(main, "AsyncWalkPlanner", FakePlanner)
    app = main.create_app(cors_origins=["http://localhost:5173"])
    app.dependency_overrides[main.get_client] = lambda: fake_client
    with TestClient(app) as client:
        yield client


def test_options_returns_walk_options_as_json(http: TestClient) -> None:
    r = http.get("/options", params={"lat": 51.515, "lon": -0.141})
    assert r.status_code == 200
    assert r.json() == [
        {
            "station_id": "940GZZLUOXC",
            "station_name": "Oxford Circus Underground Station",
            "line_id": "victoria",
            "line_name": "Victoria",
            "direction": "outbound",
            "destination_name": "Brixton Underground Station",
            "platform_name": "Southbound - Platform 5",
            "departure_time": "2026-11-23T08:05:00Z",
            "walk_seconds": 88.0,
            "wait_seconds": 200.0,
            "margin_seconds": 155.0,
        }
    ]


def test_options_defaults_match_the_cli(http: TestClient) -> None:
    http.get("/options", params={"lat": 51.5, "lon": -0.1})
    call = FakePlanner.calls[0]
    assert call["profile"] == WalkerProfile(walking_speed_kmh=5.5, risk="medium")
    assert (call["lat"], call["lon"], call["max_walk"]) == (51.5, -0.1, 12)


def test_options_passes_query_params_to_the_planner(http: TestClient) -> None:
    params = {"lat": 51.5, "lon": -0.1, "speed_kmh": 6.5, "max_walk": 8, "risk": "low"}
    assert http.get("/options", params=params).status_code == 200
    call = FakePlanner.calls[0]
    assert call["profile"] == WalkerProfile(walking_speed_kmh=6.5, risk="low")
    assert call["max_walk"] == 8


@pytest.mark.parametrize(
    "params",
    [
        {"lon": -0.1},
        {"lat": 91, "lon": -0.1},
        {"lat": 51.5, "lon": -0.1, "speed_kmh": 0},
        {"lat": 51.5, "lon": -0.1, "max_walk": 31},
        {"lat": 51.5, "lon": -0.1, "risk": "extreme"},
    ],
)
def test_options_rejects_bad_params(http: TestClient, params: dict[str, Any]) -> None:
    assert http.get("/options", params=params).status_code == 422
    assert FakePlanner.calls == []


def test_tfl_failure_is_a_502(http: TestClient) -> None:
    FakePlanner.result = TflServerError("Service Unavailable", status_code=503)
    r = http.get("/options", params={"lat": 51.5, "lon": -0.1})
    assert r.status_code == 502
    assert r.json() == {"detail": "TfL request failed: [503] Service Unavailable"}


def test_station_search(http: TestClient, fake_client: FakeClient) -> None:
    r = http.get("/stations/search", params={"q": "oxford"})
    assert r.status_code == 200
    assert r.json() == [
        {
            "id": "940GZZLUOXC",
            "name": "Oxford Circus Underground Station",
            "lat": 51.515,
            "lon": -0.1415,
        }
    ]
    assert fake_client.stops.queries == ["oxford"]


def test_station_search_needs_a_query(http: TestClient) -> None:
    assert http.get("/stations/search", params={"q": ""}).status_code == 422


def test_cors_allows_the_frontend_origin_only(http: TestClient) -> None:
    allowed = http.get("/stations/search?q=x", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = http.get("/stations/search?q=x", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_app_turns_on_the_sdk_arrivals_cache() -> None:
    app = main.create_app(arrivals_ttl_s=20)
    with TestClient(app):
        assert app.state.tfl.arrivals_cache.ttl == 20

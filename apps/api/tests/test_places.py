"""Google Places client and the /places endpoints, with Google and TfL mocked."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from stride_api import main
from stride_api.places import GooglePlaces, PlacePrediction, PlacesError
from tfl import StopSummary

GOOGLE = "https://places.googleapis.com/v1"
AUTOCOMPLETE = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "ChIJabc",
                "structuredFormat": {
                    "mainText": {"text": "BAO King's Cross"},
                    "secondaryText": {"text": "Lewis Cubitt Square, London, UK"},
                },
            }
        },
        {"queryPrediction": {"text": {"text": "bao restaurants"}}},  # not a place: skipped
    ]
}


@pytest.fixture
async def places() -> AsyncIterator[GooglePlaces]:
    async with httpx.AsyncClient() as http:
        yield GooglePlaces("test-key", http)


# ------------------------------------------------------------------ client


@respx.mock
async def test_autocomplete_request_and_parsing(places: GooglePlaces) -> None:
    route = respx.post(f"{GOOGLE}/places:autocomplete").respond(json=AUTOCOMPLETE)

    result = await places.autocomplete("bao kings", "session-1")

    assert result == [
        PlacePrediction("ChIJabc", "BAO King's Cross", "Lewis Cubitt Square, London, UK")
    ]
    request = route.calls.last.request
    assert request.headers["X-Goog-Api-Key"] == "test-key"
    assert "placePrediction.placeId" in request.headers["X-Goog-FieldMask"]
    body = json.loads(request.content)
    assert body["input"] == "bao kings"
    assert body["sessionToken"] == "session-1"
    assert body["includedRegionCodes"] == ["gb"]
    assert body["locationBias"]["circle"]["radius"] == 50_000.0


@respx.mock
async def test_location_asks_only_for_location_and_ends_session(places: GooglePlaces) -> None:
    route = respx.get(f"{GOOGLE}/places/ChIJabc").respond(
        json={"location": {"latitude": 51.5355, "longitude": -0.1256}}
    )

    assert await places.location("ChIJabc", "session-1") == (51.5355, -0.1256)

    request = route.calls.last.request
    assert request.headers["X-Goog-FieldMask"] == "location"  # Essentials, not Pro
    assert request.url.params["sessionToken"] == "session-1"


@respx.mock
async def test_google_error_message_is_kept(places: GooglePlaces) -> None:
    respx.post(f"{GOOGLE}/places:autocomplete").respond(
        403, json={"error": {"message": "API key not valid."}}
    )
    with pytest.raises(PlacesError, match="403: API key not valid"):
        await places.autocomplete("x", "s")


@respx.mock
async def test_missing_location_is_an_error(places: GooglePlaces) -> None:
    respx.get(f"{GOOGLE}/places/ChIJabc").respond(json={})
    with pytest.raises(PlacesError, match="no location"):
        await places.location("ChIJabc", "s")


# ------------------------------------------------------------------ endpoints


class FakeStops:
    async def search(self, query: str, modes: tuple[str, ...]) -> list[StopSummary]:
        assert modes == main.STATION_MODES
        return [
            StopSummary(id=f"HUB{i}", name=f"Station {i}", lat=51.5, lon=-0.1, ics_id=f"100{i}")
            for i in range(5)
        ]


class FakeClient:
    stops = FakeStops()


class FakePlaces:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sessions: list[str] = []

    async def autocomplete(self, text: str, session_token: str) -> list[PlacePrediction]:
        self.sessions.append(session_token)
        if self.fail:
            raise PlacesError("Google Places returned 429: quota")
        return [PlacePrediction("ChIJabc", "BAO King's Cross", "London")]

    async def location(self, place_id: str, session_token: str) -> tuple[float, float]:
        self.sessions.append(session_token)
        return 51.5355, -0.1256


def http_with(places: FakePlaces | None) -> TestClient:
    app = main.create_app()
    app.dependency_overrides[main.get_client] = lambda: FakeClient()
    app.dependency_overrides[main.get_places] = lambda: places
    return TestClient(app)


@pytest.fixture
def fake_places() -> FakePlaces:
    return FakePlaces()


@pytest.fixture
def http(fake_places: FakePlaces) -> Iterator[TestClient]:
    with http_with(fake_places) as client:
        yield client


def test_stations_come_first_then_google(http: TestClient, fake_places: FakePlaces) -> None:
    r = http.get("/places", params={"q": "kings", "session": "s1"})
    assert r.status_code == 200
    assert r.json() == [
        {"kind": "station", "name": "Station 0", "value": "1000"},
        {"kind": "station", "name": "Station 1", "value": "1001"},
        {"kind": "station", "name": "Station 2", "value": "1002"},
        {"kind": "place", "name": "BAO King's Cross", "detail": "London", "place_id": "ChIJabc"},
    ]
    assert fake_places.sessions == ["s1"]


def test_without_a_google_key_only_stations_are_suggested() -> None:
    with http_with(None) as http:
        r = http.get("/places", params={"q": "kings", "session": "s1"})
        assert [s["kind"] for s in r.json()] == ["station"] * 3
        assert http.get("/places/ChIJabc", params={"session": "s1"}).status_code == 503


def test_resolve_place(http: TestClient, fake_places: FakePlaces) -> None:
    r = http.get("/places/ChIJabc", params={"session": "s1"})
    assert r.json() == {"value": "51.5355,-0.1256"}
    assert fake_places.sessions == ["s1"]


def test_google_failure_is_a_502() -> None:
    with http_with(FakePlaces(fail=True)) as http:
        r = http.get("/places", params={"q": "kings", "session": "s1"})
    assert r.status_code == 502
    assert r.json() == {"detail": "Google Places returned 429: quota"}


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/places", {"q": "k", "session": "s"}),  # too short to search
        ("/places", {"q": "kings"}),  # no session
        ("/places/bad%20id", {"session": "s"}),  # not a place id
    ],
)
def test_rejects_bad_params(http: TestClient, path: str, params: dict[str, str]) -> None:
    assert http.get(path, params=params).status_code == 422

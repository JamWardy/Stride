"""JourneyPlanner against mocked TfL responses: what it fetches and the timetable top-up."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import respx
from tfl import AsyncTflClient, TflClient
from tfl_walk import AsyncJourneyPlanner, JourneyPlanner, TrainLeg, WalkerProfile

BASE = "https://api.tfl.gov.uk"
A, C, D = "STOP_A", "STOP_C", "STOP_D"
PROFILE = WalkerProfile(walking_speed_kmh=3.8)  # TfL's "average" pace, so no scaling
T0 = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def place(stop: str | None) -> dict[str, Any]:
    return {"commonName": stop or "street", "lat": 51.5, "lon": -0.1, "naptanId": stop}


def train(start: float) -> dict[str, Any]:
    return {
        "duration": 5,
        "instruction": {"summary": "Red line to C"},
        "mode": {"id": "tube", "name": "tube"},
        "departureTime": at(start),
        "arrivalTime": at(start + 5),
        "departurePoint": place(A),
        "arrivalPoint": place(C),
        "routeOptions": [{"name": "Red", "lineIdentifier": {"id": "red", "name": "Red"}}],
    }


def plan(*legs: dict[str, Any]) -> dict[str, Any]:
    journey = {
        "startDateTime": at(0),
        "arrivalDateTime": at(30),
        "duration": 30,
        "legs": list(legs),
    }
    return {"journeys": [journey]}


# 380 m takes 6 min at 3.8 km/h; TfL's 8 minutes leave 2 for the station.
WALK = {
    "duration": 8,
    "distance": 380,
    "instruction": {"summary": "Walk to A"},
    "mode": {"id": "walking", "name": "walking"},
    "departureTime": at(0),
    "arrivalTime": at(8),
    "departurePoint": place(None),
    "arrivalPoint": place(A),
}


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE) as router:
        # TfL's own plan has a train that leaves before this walker can reach it.
        router.get("/Journey/JourneyResults/51.5%2C-0.1/to/STOP_C").respond(
            json=plan(WALK, train(3))
        )
        router.get(f"/StopPoint/{A}/Arrivals").respond(json=[])  # nothing live
        for direction in ("inbound", "outbound"):
            router.get(f"/Line/red/Route/Sequence/{direction}").respond(
                json={
                    "lineId": "red",
                    "lineName": "Red",
                    "direction": direction,
                    "orderedLineRoutes": [{"name": "A-D", "naptanIds": [A, C, D]}],
                }
            )
        yield router


def test_fetches_timetable_for_a_train_beyond_live_data(api: respx.MockRouter) -> None:
    hop = api.get(f"/Journey/JourneyResults/{A}/to/{C}").respond(json=plan(train(12)))

    with TflClient(app_key="k") as client:
        [option] = JourneyPlanner(client, PROFILE).journeys("51.5,-0.1", C)

    [t] = [leg for leg in option.legs if isinstance(leg, TrainLeg)]
    assert (t.source, t.departure_time) == ("timetable", T0 + timedelta(minutes=12))
    sent = hop.calls.last.request.url.params
    assert sent["walkingSpeed"] == "average"
    assert sent["timeIs"] == "Departing"
    main = api.calls[0].request.url.params
    assert main["mode"] == "tube,dlr,overground,elizabeth-line,walking"


async def test_async_fetches_timetable_too(api: respx.MockRouter) -> None:
    api.get(f"/Journey/JourneyResults/{A}/to/{C}").respond(json=plan(train(12)))

    async with AsyncTflClient(app_key="k") as client:
        [option] = await AsyncJourneyPlanner(client, PROFILE).journeys("51.5,-0.1", C)

    assert [leg.departure_time for leg in option.legs if isinstance(leg, TrainLeg)] == [
        T0 + timedelta(minutes=12)
    ]


def test_hop_with_no_service_drops_the_journey(api: respx.MockRouter) -> None:
    api.get(f"/Journey/JourneyResults/{A}/to/{C}").respond(
        404, json={"message": "No journey found"}
    )

    with TflClient(app_key="k", max_retries=0) as client:
        assert JourneyPlanner(client, PROFILE).journeys("51.5,-0.1", C) == []

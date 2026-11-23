"""End-to-end planner tests against mocked TfL responses."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import respx
from tfl import AsyncTflClient, TflClient
from tfl_walk import AsyncWalkPlanner, WalkerProfile, WalkPlanner

BASE = "https://api.tfl.gov.uk"
LAT, LON = 51.515, -0.141
OXC, BND = "940GZZLUOXC", "940GZZLUBND"
PROFILE = WalkerProfile(walking_speed_kmh=3.6)  # 1 m/s, medium risk (45 s)


def stop(id_: str, name: str, lat: float, lon: float) -> dict[str, Any]:
    return {"id": id_, "commonName": name, "lat": lat, "lon": lon, "distance": 0}


def arrival(seconds: int) -> dict[str, Any]:
    return {
        "id": f"a{seconds}",
        "lineId": "victoria",
        "lineName": "Victoria",
        "direction": "outbound",
        "expectedArrival": "2026-11-23T08:00:00Z",
        "timeToStation": seconds,
    }


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE) as router:
        # Oxford Circus is ~67 m away (~88 s walk at 1 m/s * 1.3); Bond Street ~609 m (~792 s).
        router.get("/StopPoint").respond(
            json={
                "stopPoints": [
                    stop(OXC, "Oxford Circus", 51.515224, -0.141903),
                    stop(BND, "Bond Street", 51.514304, -0.149723),
                ]
            }
        )
        router.get(f"/StopPoint/{OXC}/Arrivals").respond(json=[arrival(300)])
        yield router


def test_options_from(api: respx.MockRouter) -> None:
    with TflClient(app_key="k") as client:
        options = WalkPlanner(client, PROFILE).options_from(LAT, LON, max_walk_minutes=10)

    nearby = api.calls[0].request.url.params
    assert nearby["radius"] == "600"  # 1 m/s * 10 min
    # Bond Street is inside the straight-line radius but too far once streets are allowed
    # for, so its arrivals are never fetched (respx would fail on an unmocked route).
    [opt] = options
    assert opt.station_id == OXC
    assert opt.walk_seconds == pytest.approx(87.5, abs=0.5)
    assert opt.wait_seconds == pytest.approx(300 - opt.walk_seconds - 120)


def test_entry_buffer_override(api: respx.MockRouter) -> None:
    with TflClient(app_key="k") as client:
        planner = WalkPlanner(client, PROFILE, entry_buffers={OXC: 250})
        assert planner.options_from(LAT, LON, max_walk_minutes=10) == []  # 88 + 250 + 45 > 300


async def test_async_matches_sync(api: respx.MockRouter) -> None:
    with TflClient(app_key="k") as client:
        expected = WalkPlanner(client, PROFILE).options_from(LAT, LON, 10)
    async with AsyncTflClient(app_key="k") as aclient:
        assert await AsyncWalkPlanner(aclient, PROFILE).options_from(LAT, LON, 10) == expected


def test_max_walk_must_be_positive() -> None:
    with TflClient(app_key="k") as client, pytest.raises(ValueError, match="max_walk"):
        WalkPlanner(client, PROFILE).options_from(LAT, LON, max_walk_minutes=0)

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from tfl import AsyncTflClient, TflClient, TflNotFoundError
from tfl_test_support import load

OXC = "940GZZLUOXC"


def test_search(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/StopPoint/Search/oxford%20circus").respond(json=load("stop_search.json"))

    stops = client.stops.search("oxford circus")

    assert route.calls.last.request.url.params["modes"] == "tube"
    assert route.calls.last.request.url.params["app_key"] == "test-key"
    [stop] = stops
    assert stop.id == OXC
    assert stop.name == "Oxford Circus Underground Station"
    assert stop.modes == ["tube"]
    assert stop.zone == "1"
    assert stop.ics_id == "1000173"


def test_search_encodes_path_and_allows_all_modes(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/StopPoint/Search/King%27s%20Cross%2FSt%20Pancras").respond(
        json={"matches": []}
    )

    assert client.stops.search("King's Cross/St Pancras", modes=()) == []
    assert "modes" not in route.calls.last.request.url.params


def test_single_string_filters_are_not_split(client: TflClient, api: respx.MockRouter) -> None:
    search = api.get("/StopPoint/Search/x").respond(json={"matches": []})
    nearby = api.get("/StopPoint").respond(json={"stopPoints": []})

    client.stops.search("x", modes="bus")
    client.stops.nearby(51.5, -0.1, stop_types="NaptanPublicBusCoachTram")

    assert search.calls.last.request.url.params["modes"] == "bus"
    assert nearby.calls.last.request.url.params["stopTypes"] == "NaptanPublicBusCoachTram"


def test_nearby(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/StopPoint").respond(json=load("stops_nearby.json"))

    stops = client.stops.nearby(51.515, -0.141, radius_m=800)

    params = route.calls.last.request.url.params
    assert params["lat"] == "51.515"
    assert params["lon"] == "-0.141"
    assert params["radius"] == "800"
    assert params["stopTypes"] == "NaptanMetroStation"
    assert [s.id for s in stops][:2] == [OXC, "940GZZLUBND"]
    assert stops[0].distance_m == pytest.approx(67.32, abs=0.01)
    assert {line.id for line in stops[0].lines} == {"bakerloo", "central", "victoria"}


@pytest.mark.parametrize("stop_types", [(), "", []])
def test_nearby_rejects_empty_stop_types(
    client: TflClient, api: respx.MockRouter, stop_types: tuple[str, ...] | str | list[str]
) -> None:
    route = api.get("/StopPoint")
    with pytest.raises(ValueError):
        client.stops.nearby(51.5, -0.1, stop_types=stop_types)
    assert not route.called


def test_get(client: TflClient, api: respx.MockRouter) -> None:
    api.get(f"/StopPoint/{OXC}").respond(json=load("stop_get.json"))

    stop = client.stops.get(OXC)

    assert stop.name == "Oxford Circus Underground Station"
    assert stop.stop_type == "NaptanMetroStation"
    assert [line.name for line in stop.lines] == ["Bakerloo", "Central", "Victoria"]
    assert stop.line_mode_groups[0].line_ids == ["bakerloo", "central", "victoria"]
    assert len(stop.children) == 15
    assert any(p.key == "Night" for p in stop.additional_properties)


def test_get_not_found(client: TflClient, api: respx.MockRouter) -> None:
    api.get("/StopPoint/NOPE").respond(404, json=load("stop_not_found.json"))

    with pytest.raises(TflNotFoundError) as info:
        client.stops.get("NOPE")

    assert info.value.status_code == 404
    assert "not recognised" in info.value.message
    assert info.value.body["exceptionType"] == "EntityNotFoundException"


def test_arrivals_sorted_and_parsed(client: TflClient, api: respx.MockRouter) -> None:
    raw = load("stop_arrivals.json")
    api.get(f"/StopPoint/{OXC}/Arrivals").respond(json=raw)

    arrivals = client.stops.arrivals(OXC)

    assert len(arrivals) == len(raw)
    times = [a.time_to_station for a in arrivals]
    assert times == sorted(times)
    first = arrivals[0]
    assert first.line_id == "victoria"
    assert first.platform_name == "Northbound - Platform 6"
    assert first.direction == "outbound"
    assert first.destination_name == "Walthamstow Central Underground Station"
    assert first.expected_arrival == datetime(2026, 11, 23, 21, 0, 17, tzinfo=UTC)
    assert first.expected_arrival.tzinfo is not None
    assert first.time_to_station == 59
    assert first.minutes_away == 0


def test_arrival_tolerates_missing_and_empty_fields(
    client: TflClient, api: respx.MockRouter
) -> None:
    sparse = {
        "id": "1",
        "lineId": "25",
        "lineName": "25",
        "expectedArrival": "2026-11-23T21:00:00Z",
        "timeToStation": 185,
        "platformName": "",
        "someNewField": {"x": 1},
    }
    api.get("/StopPoint/X/Arrivals").respond(json=[sparse])

    [arrival] = client.stops.arrivals("X")

    assert arrival.platform_name is None
    assert arrival.direction is None
    assert arrival.minutes_away == 3


async def test_async_methods(aclient: AsyncTflClient, api: respx.MockRouter) -> None:
    api.get("/StopPoint/Search/oxford").respond(json=load("stop_search.json"))
    api.get("/StopPoint").respond(json=load("stops_nearby.json"))
    api.get(f"/StopPoint/{OXC}").respond(json=load("stop_get.json"))
    api.get(f"/StopPoint/{OXC}/Arrivals").respond(json=load("stop_arrivals.json"))

    assert (await aclient.stops.search("oxford"))[0].id == OXC
    assert (await aclient.stops.nearby(51.515, -0.141))[0].id == OXC
    assert (await aclient.stops.get(OXC)).id == OXC
    arrivals = await aclient.stops.arrivals(OXC)
    assert [a.time_to_station for a in arrivals] == sorted(a.time_to_station for a in arrivals)


def test_naive_timestamps_are_london_time() -> None:
    from tfl.models._base import LONDON
    from tfl.models.stops import Arrival

    a = Arrival.model_validate(
        {
            "id": "1",
            "lineId": "x",
            "lineName": "x",
            "timeToStation": 0,
            "expectedArrival": "2026-07-01T09:00:00",
            "timestamp": "0001-01-01T00:00:00",
        }
    )
    assert a.expected_arrival.tzinfo is LONDON
    assert a.expected_arrival.utcoffset() is not None
    assert a.timestamp is None


def test_http_error_body_can_be_text(client: TflClient, api: respx.MockRouter) -> None:
    api.get(f"/StopPoint/{OXC}").mock(return_value=httpx.Response(404, text="gone"))
    with pytest.raises(TflNotFoundError) as info:
        client.stops.get(OXC)
    assert info.value.body == "gone"

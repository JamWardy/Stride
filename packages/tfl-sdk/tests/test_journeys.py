from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import respx
from tfl import AsyncTflClient, TflAmbiguousLocationError, TflClient, TflError
from tfl_test_support import load

OXC = "940GZZLUOXC"
BNK = "940GZZLUBNK"
LONDON = ZoneInfo("Europe/London")


def test_plan(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get(f"/Journey/JourneyResults/{OXC}/to/{BNK}").respond(
        json=load("journey_results.json")
    )

    journeys = client.journeys.plan(OXC, BNK)

    assert "date" not in route.calls.last.request.url.params
    assert len(journeys) == 3
    journey = journeys[0]
    assert journey.start_time == datetime(2026, 11, 23, 21, 1, tzinfo=LONDON)
    assert journey.duration_minutes == 8
    assert journey.fare is not None
    assert journey.fare.total_cost_pence == 300
    [leg] = journey.legs
    assert leg.mode.id == "tube"
    assert leg.instruction.summary == "Central line to Bank"
    assert leg.departure_point.naptan_id == OXC
    assert leg.arrival_point.name == "Bank Underground Station"
    assert leg.route_options[0].line is not None
    assert leg.route_options[0].line.id == "central"
    assert leg.is_disrupted
    assert leg.disruptions[0].created == datetime(2026, 11, 23, 16, 57, tzinfo=LONDON)


def test_plan_encodes_places(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/Journey/JourneyResults/51.515%2C-0.141/to/King%27s%20Cross").respond(
        json={"journeys": []}
    )
    assert client.journeys.plan("51.515,-0.141", "King's Cross") == []
    assert route.called


@pytest.mark.parametrize(
    ("depart_at", "date", "time"),
    [
        (datetime(2026, 7, 1, 9, 30), "20260701", "0930"),  # naive = London
        (datetime(2026, 7, 1, 8, 30, tzinfo=UTC), "20260701", "0930"),  # BST
        (datetime(2026, 12, 31, 23, 45, tzinfo=UTC), "20261231", "2345"),  # GMT
    ],
)
def test_plan_depart_at_is_sent_as_london_time(
    client: TflClient, api: respx.MockRouter, depart_at: datetime, date: str, time: str
) -> None:
    route = api.get(f"/Journey/JourneyResults/{OXC}/to/{BNK}").respond(json={"journeys": []})

    client.journeys.plan(OXC, BNK, depart_at=depart_at)

    params = route.calls.last.request.url.params
    assert (params["date"], params["time"], params["timeIs"]) == (date, time, "Departing")


def test_plan_ambiguous_raises_with_options(client: TflClient, api: respx.MockRouter) -> None:
    api.get("/Journey/JourneyResults/oxford/to/bank").respond(
        300, json=load("journey_ambiguous.json")
    )

    with pytest.raises(TflAmbiguousLocationError) as info:
        client.journeys.plan("oxford", "bank")

    error = info.value
    assert error.status_code == 300
    assert isinstance(error.body, dict)
    assert len(error.from_options) == 20
    assert len(error.to_options) == 20
    assert error.via_options == []
    best = error.to_options[0]
    assert best.parameter_value == "1000013"
    assert best.place.name == "City of London, Bank"
    assert best.place.modes == ["dlr", "tube"]
    assert "from 'oxford' (20 options)" in str(error)
    assert "to 'bank' (20 options)" in str(error)


def test_plan_300_without_disambiguation_body_is_plain_error(
    client: TflClient, api: respx.MockRouter
) -> None:
    api.get("/Journey/JourneyResults/a/to/b").respond(300, text="odd")
    with pytest.raises(TflError) as info:
        client.journeys.plan("a", "b")
    assert type(info.value) is TflError
    assert info.value.status_code == 300


def test_plan_ambiguity_is_not_retried(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get("/Journey/JourneyResults/oxford/to/bank").respond(
        300, json=load("journey_ambiguous.json")
    )
    with pytest.raises(TflAmbiguousLocationError):
        client.journeys.plan("oxford", "bank")
    assert route.call_count == 1
    assert sleeps == []


async def test_async_plan(aclient: AsyncTflClient, api: respx.MockRouter) -> None:
    api.get(f"/Journey/JourneyResults/{OXC}/to/{BNK}").respond(json=load("journey_results.json"))
    api.get("/Journey/JourneyResults/oxford/to/bank").respond(
        300, json=load("journey_ambiguous.json")
    )

    assert len(await aclient.journeys.plan(OXC, BNK)) == 3
    with pytest.raises(TflAmbiguousLocationError):
        await aclient.journeys.plan("oxford", "bank")

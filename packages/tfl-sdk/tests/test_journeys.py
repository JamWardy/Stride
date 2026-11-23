from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import respx
from tfl import AsyncTflClient, TflAmbiguousLocationError, TflClient
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


def test_plan_300_without_readable_body_is_still_ambiguous_error(
    client: TflClient, api: respx.MockRouter
) -> None:
    api.get("/Journey/JourneyResults/a/to/b").respond(300, text="odd")
    with pytest.raises(TflAmbiguousLocationError) as info:
        client.journeys.plan("a", "b")
    error = info.value
    assert error.status_code == 300
    assert error.body == "odd"
    assert error.from_options == error.to_options == error.via_options == []


def test_plan_300_keeps_valid_sections_when_one_is_malformed(
    client: TflClient, api: respx.MockRouter
) -> None:
    body = load("journey_ambiguous.json")
    body["fromLocationDisambiguation"]["disambiguationOptions"] = [{"bogus": True}]
    api.get("/Journey/JourneyResults/a/to/b").respond(300, json=body)
    with pytest.raises(TflAmbiguousLocationError) as info:
        client.journeys.plan("a", "b")
    assert info.value.from_options == []
    assert info.value.to_options


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


def test_plan_parses_walks_and_changes(client: TflClient, api: respx.MockRouter) -> None:
    # Recorded from a street address near Baker Street to one near Westferry.
    api.get(url__regex=r"/Journey/JourneyResults/.*").respond(json=load("journey_walk_change.json"))

    [first, *_] = client.journeys.plan("51.5226,-0.1571", "51.5085,-0.0255")

    walk, bakerloo, central, dlr, last_walk = first.legs
    assert walk.mode.id == "walking"
    assert walk.distance_m == 208.0
    assert walk.departure_point.naptan_id is None
    assert walk.arrival_point.naptan_id == "940GZZLUBST"
    assert len(walk.instruction.steps) == 7
    assert all(step.distance_m is not None for step in walk.instruction.steps)
    assert walk.path is not None
    assert walk.path.stops == []

    assert bakerloo.path is not None
    assert [s.id for s in bakerloo.path.stops] == ["940GZZLURGP", OXC]
    assert bakerloo.route_options[0].directions == ["Elephant & Castle Underground Station"]
    # A change of trains has no walking leg: it is the gap between two legs.
    assert central.departure_point.naptan_id == OXC
    assert central.departure_time > bakerloo.arrival_time
    assert dlr.departure_point.naptan_id == "940GZZDLBNK"
    assert last_walk.arrival_point.naptan_id is None


def test_plan_sends_modes_and_walking_speed(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get(f"/Journey/JourneyResults/{OXC}/to/{BNK}").respond(json={"journeys": []})

    client.journeys.plan(OXC, BNK, modes=("tube", "dlr", "walking"), walking_speed="fast")

    params = route.calls.last.request.url.params
    assert (params["mode"], params["walkingSpeed"]) == ("tube,dlr,walking", "fast")


def test_plan_leaves_modes_and_speed_to_tfl_by_default(
    client: TflClient, api: respx.MockRouter
) -> None:
    route = api.get(f"/Journey/JourneyResults/{OXC}/to/{BNK}").respond(json={"journeys": []})
    client.journeys.plan(OXC, BNK)
    params = route.calls.last.request.url.params
    assert "mode" not in params
    assert "walkingSpeed" not in params


def test_plan_rejects_unknown_walking_speed(client: TflClient) -> None:
    with pytest.raises(ValueError, match="walking_speed"):
        client.journeys.plan(OXC, BNK, walking_speed="brisk")  # type: ignore[arg-type]

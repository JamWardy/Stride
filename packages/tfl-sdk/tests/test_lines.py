from __future__ import annotations

from datetime import UTC, datetime

import pytest
import respx
from tfl import AsyncTflClient, TflClient
from tfl_test_support import load


def test_status(client: TflClient, api: respx.MockRouter) -> None:
    api.get("/Line/Mode/tube/Status").respond(json=load("line_status.json"))

    lines = client.lines.status()

    assert len(lines) == 11
    bakerloo = next(line for line in lines if line.id == "bakerloo")
    assert bakerloo.name == "Bakerloo"
    assert bakerloo.mode_name == "tube"
    [good] = bakerloo.statuses
    assert (good.severity, good.description) == (10, "Good Service")
    assert good.reason is None
    assert good.disruption is None

    central = next(line for line in lines if line.id == "central")
    [delayed] = central.statuses
    assert delayed.description == "Minor Delays"
    assert delayed.reason is not None
    assert delayed.reason.startswith("Central Line: Minor delays")
    [period] = delayed.validity_periods
    assert period.from_date == datetime(2026, 11, 23, 16, 55, 39, tzinfo=UTC)
    assert period.is_now
    assert delayed.disruption is not None
    assert delayed.disruption.category == "RealTime"


def test_status_several_modes(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/Line/Mode/tube%2Cdlr/Status").respond(json=[])
    assert client.lines.status(("tube", "dlr")) == []
    assert route.called


def test_status_single_mode_string(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get("/Line/Mode/dlr/Status").respond(json=[])
    client.lines.status("dlr")
    assert route.called


@pytest.mark.parametrize("modes", [(), ""])
def test_status_rejects_empty_modes(client: TflClient, modes: tuple[str, ...] | str) -> None:
    with pytest.raises(ValueError):
        client.lines.status(modes)


def test_disruptions(client: TflClient, api: respx.MockRouter) -> None:
    api.get("/Line/central/Disruption").respond(json=load("line_disruption.json"))

    [disruption] = client.lines.disruptions("central")

    assert disruption.type == "lineInfo"
    assert disruption.category == "RealTime"
    assert disruption.description is not None
    assert disruption.description.startswith("Central Line: Minor delays")


async def test_async_lines(aclient: AsyncTflClient, api: respx.MockRouter) -> None:
    api.get("/Line/Mode/tube/Status").respond(json=load("line_status.json"))
    api.get("/Line/central/Disruption").respond(json=load("line_disruption.json"))

    assert len(await aclient.lines.status()) == 11
    assert len(await aclient.lines.disruptions("central")) == 1

from __future__ import annotations

from collections.abc import Iterator

import cli
import pytest
import respx

BASE = "https://api.tfl.gov.uk"
OXC = "940GZZLUOXC"

SEARCH = {
    "matches": [
        {"id": OXC, "name": "Oxford Circus Underground Station", "lat": 51.515, "lon": -0.1415}
    ]
}
NEARBY = {
    "stopPoints": [
        {
            "id": OXC,
            "commonName": "Oxford Circus Underground Station",
            "lat": 51.515,
            "lon": -0.1415,
            "distance": 0.0,
        }
    ]
}
# Walk 0 s + 120 s entry buffer + 45 s medium margin: 600 s away is catchable with
# 480 s (8 min) on the platform and 435 s (7 min) to spare; 100 s away is not.
ARRIVALS = [
    {
        "id": "1",
        "lineId": "central",
        "lineName": "Central",
        "expectedArrival": "2026-11-23T21:55:00Z",
        "timeToStation": 600,
        "destinationName": "Epping Underground Station",
        "platformName": "Eastbound - Platform 2",
    },
    {
        "id": "2",
        "lineId": "victoria",
        "lineName": "Victoria",
        "expectedArrival": "2026-11-23T21:46:40Z",
        "timeToStation": 100,
        "destinationName": "Brixton Underground Station",
    },
]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    monkeypatch.delenv("TFL_APP_KEY", raising=False)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


def test_station_lists_catchable_trains(
    api: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    search = api.get("/StopPoint/Search/Oxford%20Circus").respond(json=SEARCH)
    nearby = api.get("/StopPoint").respond(json=NEARBY)
    api.get(f"/StopPoint/{OXC}/Arrivals").respond(json=ARRIVALS)

    assert cli.main(["--station", "Oxford Circus"]) == 0

    out = capsys.readouterr().out
    assert search.called
    assert nearby.calls.last.request.url.params["lat"] == "51.515"
    assert "From Oxford Circus, walking at 5.5 km/h" in out
    rows = [line.split() for line in out.splitlines() if line.startswith("21:")]
    assert rows == [
        ["21:55", "Oxford", "Circus", "Central", "Epping", "Eastbound", "-", "Platform", "2",
         "0", "min", "8", "min", "7", "min"],
    ]  # fmt: skip


def test_nothing_catchable(api: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    api.get("/StopPoint").respond(json=NEARBY)
    api.get(f"/StopPoint/{OXC}/Arrivals").respond(json=[])

    assert cli.main(["--lat", "51.515", "--lon", "-0.1415"]) == 0
    assert "No catchable trains" in capsys.readouterr().out


def test_unknown_station_is_a_usage_error(
    api: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    api.get("/StopPoint/Search/Nowhere").respond(json={"matches": []})
    with pytest.raises(SystemExit) as info:
        cli.main(["--station", "Nowhere"])
    assert info.value.code == 2
    assert "no tube station found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--lat", "51.5"],
        ["--station", "Bank", "--lat", "51.5", "--lon", "-0.1"],
        ["--lat", "51.5", "--lon", "-0.1", "--speed", "0"],
        ["--lat", "51.5", "--lon", "-0.1", "--max-walk", "-1"],
        ["--lat", "51.5", "--lon", "-0.1", "--risk", "extreme"],
    ],
)
def test_bad_arguments_exit_with_usage_error(api: respx.MockRouter, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(argv)
    assert info.value.code == 2
    assert not api.calls


def test_tfl_error_exits_1(api: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    api.get("/StopPoint").respond(403, json={"message": "Invalid app_key"})
    assert cli.main(["--lat", "51.5", "--lon", "-0.1"]) == 1
    assert "TfL request failed: [403] Invalid app_key" in capsys.readouterr().err


def test_short_name() -> None:
    assert cli.short_name("Bank Underground Station") == "Bank"
    assert cli.short_name("Bank DLR Station") == "Bank DLR Station"
    assert cli.short_name("Northbound") == "Northbound"

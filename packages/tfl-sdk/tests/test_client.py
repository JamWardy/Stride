from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx
from tfl import (
    AsyncTflClient,
    TflAuthError,
    TflClient,
    TflError,
    TflNotFoundError,
    TflRateLimitError,
    TflServerError,
)
from tfl._core import RetryPolicy, TTLCache, parse_retry_after
from tfl_test_support import load

OXC = "940GZZLUOXC"
ARRIVALS = f"/StopPoint/{OXC}/Arrivals"


# ------------------------------------------------------------------ app key


def test_app_key_from_env(monkeypatch: pytest.MonkeyPatch, api: respx.MockRouter) -> None:
    monkeypatch.setenv("TFL_APP_KEY", "env-key")
    route = api.get(ARRIVALS).respond(json=[])
    with TflClient() as client:
        client.stops.arrivals(OXC)
    assert route.calls.last.request.url.params["app_key"] == "env-key"


def test_no_app_key_is_anonymous(api: respx.MockRouter) -> None:
    route = api.get(ARRIVALS).respond(json=[])
    with TflClient() as client:
        client.stops.arrivals(OXC)
    assert "app_key" not in route.calls.last.request.url.params


def test_error_url_has_app_key_removed(client: TflClient, api: respx.MockRouter) -> None:
    api.get(ARRIVALS).respond(403, json={"message": "Invalid app_key"})
    with pytest.raises(TflAuthError) as info:
        client.stops.arrivals(OXC)
    assert info.value.url is not None
    assert "test-key" not in info.value.url


# ------------------------------------------------------------------ error mapping


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, TflError),
        (401, TflAuthError),
        (403, TflAuthError),
        (404, TflNotFoundError),
        (429, TflRateLimitError),
        (500, TflServerError),
        (503, TflServerError),
    ],
)
def test_error_mapping(status: int, error_type: type[TflError], api: respx.MockRouter) -> None:
    api.get(ARRIVALS).respond(status, json={"message": "boom"})
    with TflClient(max_retries=0) as client, pytest.raises(error_type) as info:
        client.stops.arrivals(OXC)
    assert type(info.value) is error_type
    assert info.value.status_code == status
    assert info.value.body == {"message": "boom"}
    assert str(info.value) == f"[{status}] boom"


def test_rate_limit_error_carries_retry_after(api: respx.MockRouter) -> None:
    api.get(ARRIVALS).respond(429, headers={"Retry-After": "7"})
    with TflClient(max_retries=0) as client, pytest.raises(TflRateLimitError) as info:
        client.stops.arrivals(OXC)
    assert info.value.retry_after == 7


# ------------------------------------------------------------------ retries


def test_retries_5xx_then_succeeds(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).mock(
        side_effect=[httpx.Response(502), httpx.Response(503), httpx.Response(200, json=[])]
    )
    assert client.stops.arrivals(OXC) == []
    assert route.call_count == 3
    assert len(sleeps) == 2


def test_gives_up_after_max_retries(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).respond(500)
    with pytest.raises(TflServerError):
        client.stops.arrivals(OXC)
    assert route.call_count == 4  # 1 + max_retries
    assert len(sleeps) == 3


def test_respects_retry_after(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    api.get(ARRIVALS).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json=[]),
        ]
    )
    client.stops.arrivals(OXC)
    assert sleeps == [2.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_no_retry_on_other_4xx(
    status: int, client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).respond(status)
    with pytest.raises(TflError):
        client.stops.arrivals(OXC)
    assert route.call_count == 1
    assert sleeps == []


def test_retries_timeouts(client: TflClient, api: respx.MockRouter, sleeps: list[float]) -> None:
    route = api.get(ARRIVALS).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json=[])]
    )
    assert client.stops.arrivals(OXC) == []
    assert route.call_count == 2


def test_timeout_exhausted_raises_tfl_error(api: respx.MockRouter, sleeps: list[float]) -> None:
    route = api.get(ARRIVALS).mock(side_effect=httpx.ConnectTimeout("slow"))
    with TflClient(max_retries=2) as client, pytest.raises(TflError) as info:
        client.stops.arrivals(OXC)
    assert route.call_count == 3
    assert info.value.status_code is None
    assert isinstance(info.value.__cause__, httpx.TimeoutException)


def test_transport_error_has_redacted_url(api: respx.MockRouter) -> None:
    api.get("/StopPoint").mock(side_effect=httpx.ConnectError("refused"))
    with TflClient(app_key="secret", max_retries=0) as client, pytest.raises(TflError) as info:
        client.stops.nearby(51.5, -0.1)
    assert info.value.url is not None
    url = httpx.URL(info.value.url)
    assert url.path == "/StopPoint"
    assert url.params["stopTypes"] == "NaptanMetroStation"
    assert "app_key" not in url.params


def test_max_retries_zero(api: respx.MockRouter, sleeps: list[float]) -> None:
    route = api.get(ARRIVALS).respond(503)
    with TflClient(max_retries=0) as client, pytest.raises(TflServerError):
        client.stops.arrivals(OXC)
    assert route.call_count == 1


async def test_async_retries(
    aclient: AsyncTflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(500), httpx.Response(200, json=[])]
    )
    assert await aclient.stops.arrivals(OXC) == []
    assert route.call_count == 3
    assert len(sleeps) == 2


async def test_async_error_mapping(aclient: AsyncTflClient, api: respx.MockRouter) -> None:
    api.get(f"/StopPoint/{OXC}").respond(404, json=load("stop_not_found.json"))
    with pytest.raises(TflNotFoundError):
        await aclient.stops.get(OXC)


def test_backoff_grows_exponentially_with_jitter_and_cap() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0)
    for attempt, cap in [(0, 1.0), (1, 2.0), (2, 4.0), (5, 4.0)]:
        delays = {policy.backoff(attempt) for _ in range(50)}
        assert all(cap / 2 <= d <= cap for d in delays)
        assert len(delays) > 1  # jittered


def test_parse_retry_after() -> None:
    assert parse_retry_after(None) is None
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("garbage") is None
    now = datetime(2026, 1, 1, tzinfo=UTC)
    header = format_datetime(now + timedelta(seconds=30), usegmt=True)
    assert parse_retry_after(header, now=now.timestamp()) == pytest.approx(30)


# ------------------------------------------------------------------ cache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ttl_cache_expires() -> None:
    clock = FakeClock()
    cache = TTLCache(10, clock=clock)
    cache.set("k", 1)
    assert cache.get("k") == (True, 1)
    clock.now = 9.9
    assert cache.get("k") == (True, 1)
    clock.now = 10
    assert cache.get("k") == (False, None)


def test_ttl_cache_reports_age() -> None:
    clock = FakeClock()
    cache = TTLCache(10, clock=clock)
    assert cache.get_with_age("k") == (False, None, 0.0)
    cache.set("k", 1)
    clock.now = 4.5
    assert cache.get_with_age("k") == (True, 1, 4.5)


def test_cache_off_by_default(client: TflClient, api: respx.MockRouter) -> None:
    route = api.get(f"/StopPoint/{OXC}").respond(json=load("stop_get.json"))
    client.stops.get(OXC)
    client.stops.get(OXC)
    assert route.call_count == 2


def test_cache_get_and_search_until_ttl(api: respx.MockRouter) -> None:
    get_route = api.get(f"/StopPoint/{OXC}").respond(json=load("stop_get.json"))
    search_route = api.get("/StopPoint/Search/oxford").respond(json=load("stop_search.json"))
    clock = FakeClock()
    with TflClient(cache_ttl=60) as client:
        assert client.cache is not None
        client.cache._clock = clock

        first = client.stops.get(OXC)
        assert client.stops.get(OXC) == first
        client.stops.search("oxford")
        client.stops.search("oxford")
        client.stops.search("oxford", modes=("bus",))  # different params, different key
        assert get_route.call_count == 1
        assert search_route.call_count == 2

        clock.now = 61
        client.stops.get(OXC)
        assert get_route.call_count == 2


def test_cache_ttl_does_not_cache_arrivals(api: respx.MockRouter) -> None:
    route = api.get(ARRIVALS).respond(json=[])
    with TflClient(cache_ttl=60) as client:
        client.stops.arrivals(OXC)
        client.stops.arrivals(OXC)
    assert route.call_count == 2


def arrival(seconds: int) -> dict[str, object]:
    return {
        "id": f"a{seconds}",
        "lineId": "victoria",
        "lineName": "Victoria",
        "expectedArrival": "2026-11-23T08:00:00Z",
        "timeToStation": seconds,
    }


def test_arrivals_cache_ages_results_until_ttl(api: respx.MockRouter) -> None:
    route = api.get(ARRIVALS).respond(json=[arrival(300), arrival(120)])
    clock = FakeClock()
    with TflClient(arrivals_cache_ttl=20) as client:
        assert client.arrivals_cache is not None
        assert client.cache is None  # independent of cache_ttl
        client.arrivals_cache._clock = clock

        assert [a.time_to_station for a in client.stops.arrivals(OXC)] == [120, 300]
        clock.now = 12.2  # rounded up: a cached train never looks further away than it is
        assert [a.time_to_station for a in client.stops.arrivals(OXC)] == [107, 287]
        assert route.call_count == 1

        clock.now = 20
        assert [a.time_to_station for a in client.stops.arrivals(OXC)] == [120, 300]
        assert route.call_count == 2


def test_arrivals_cache_skips_errors(api: respx.MockRouter) -> None:
    route = api.get(ARRIVALS).mock(
        side_effect=[httpx.Response(404), httpx.Response(200, json=[arrival(60)])]
    )
    with TflClient(arrivals_cache_ttl=20) as client:
        with pytest.raises(TflNotFoundError):
            client.stops.arrivals(OXC)
        assert client.stops.arrivals(OXC)[0].time_to_station == 60
    assert route.call_count == 2


async def test_async_arrivals_cache(api: respx.MockRouter) -> None:
    route = api.get(ARRIVALS).respond(json=[arrival(60)])
    async with AsyncTflClient(arrivals_cache_ttl=20) as client:
        await client.stops.arrivals(OXC)
        await client.stops.arrivals(OXC)
    assert route.call_count == 1


def test_errors_are_not_cached(api: respx.MockRouter) -> None:
    route = api.get(f"/StopPoint/{OXC}").mock(
        side_effect=[httpx.Response(404), httpx.Response(200, json=load("stop_get.json"))]
    )
    with TflClient(cache_ttl=60) as client:
        with pytest.raises(TflNotFoundError):
            client.stops.get(OXC)
        assert client.stops.get(OXC).id == OXC
    assert route.call_count == 2


async def test_async_cache(api: respx.MockRouter) -> None:
    route = api.get(f"/StopPoint/{OXC}").respond(json=load("stop_get.json"))
    async with AsyncTflClient(cache_ttl=60) as client:
        await client.stops.get(OXC)
        await client.stops.get(OXC)
    assert route.call_count == 1


# ------------------------------------------------------------------ lifecycle


def test_context_manager_closes() -> None:
    client = TflClient()
    with client:
        pass
    assert client._http.is_closed


async def test_async_context_manager_closes() -> None:
    client = AsyncTflClient()
    async with client:
        pass
    assert client._http.is_closed


def test_rejects_negative_retries() -> None:
    with pytest.raises(ValueError):
        TflClient(max_retries=-1)


@pytest.mark.parametrize("timeout", [0, -1])
def test_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        TflClient(timeout=timeout)


# ------------------------------------------------------------------ transport and body errors


def test_retries_connection_errors(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json=[])]
    )
    assert client.stops.arrivals(OXC) == []
    assert route.call_count == 2


def test_connection_error_exhausted_raises_tfl_error(
    api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).mock(side_effect=httpx.ConnectError("refused"))
    with TflClient(max_retries=1) as client, pytest.raises(TflError) as info:
        client.stops.arrivals(OXC)
    assert route.call_count == 2
    assert info.value.status_code is None
    assert "failed after 1 retries" in str(info.value)
    assert isinstance(info.value.__cause__, httpx.ConnectError)


async def test_async_connection_error_raises_tfl_error(
    aclient: AsyncTflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    api.get(ARRIVALS).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(TflError):
        await aclient.stops.arrivals(OXC)


def test_non_json_success_raises_tfl_error(client: TflClient, api: respx.MockRouter) -> None:
    api.get(ARRIVALS).respond(200, text="<html>maintenance</html>")
    with pytest.raises(TflError) as info:
        client.stops.arrivals(OXC)
    assert info.value.status_code == 200
    assert info.value.body == "<html>maintenance</html>"
    assert info.value.url is not None
    assert "test-key" not in info.value.url


def test_long_retry_after_is_not_waited_for(
    client: TflClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get(ARRIVALS).respond(429, headers={"Retry-After": "3600"})
    with pytest.raises(TflRateLimitError) as info:
        client.stops.arrivals(OXC)
    assert route.call_count == 1
    assert sleeps == []
    assert info.value.retry_after == 3600


def test_ttl_cache_drops_expired_entries_on_set() -> None:
    clock = FakeClock()
    cache = TTLCache(10, clock=clock)
    cache.set("old", 1)
    clock.now = 10
    cache.set("new", 2)
    assert list(cache._entries) == ["new"]


def test_ttl_cache_is_thread_safe() -> None:
    # A tiny TTL means every set() sweeps expired entries while other threads read and
    # write; without the lock this raised RuntimeError / KeyError.
    cache = TTLCache(1e-6)
    errors: list[BaseException] = []

    def hammer(n: int) -> None:
        try:
            for i in range(5000):
                cache.set((n, i), i)
                cache.get((n, i - 1))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(8)]
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads very often so a race shows up reliably
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(interval)
    assert errors == []


def test_version_matches_package_metadata() -> None:
    from importlib.metadata import version

    import tfl
    from tfl._core import USER_AGENT

    assert tfl.__version__ == version("tfl-sdk")
    assert USER_AGENT.startswith(f"tfl-sdk/{tfl.__version__} ")


# ------------------------------------------------------------------ unexpected response shapes


@pytest.mark.parametrize(
    ("path", "payload", "call"),
    [
        (ARRIVALS, [{"id": "1"}], lambda c: c.stops.arrivals(OXC)),  # missing required fields
        ("/StopPoint/Search/oxford", [], lambda c: c.stops.search("oxford")),  # list, not object
    ],
)
def test_unparseable_response_raises_tfl_error(
    path: str, payload: object, call: Callable[[TflClient], object], api: respx.MockRouter
) -> None:
    api.get(path).respond(json=payload)
    with TflClient(max_retries=0) as client, pytest.raises(TflError) as info:
        call(client)
    assert type(info.value) is TflError
    assert info.value.status_code == 200
    assert info.value.body == payload


def test_unparseable_response_is_not_cached(api: respx.MockRouter) -> None:
    route = api.get("/StopPoint/Search/oxford")
    route.side_effect = [httpx.Response(200, json=[]), httpx.Response(200, json={"matches": []})]
    with TflClient(cache_ttl=60) as client:
        with pytest.raises(TflError):
            client.stops.search("oxford")
        assert client.stops.search("oxford") == []
    assert route.call_count == 2

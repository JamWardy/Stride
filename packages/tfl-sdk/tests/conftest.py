from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import respx
from tfl import AsyncTflClient, TflClient
from tfl_test_support import BASE


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFL_APP_KEY", raising=False)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace sync and async sleeps with recorders so retry tests run instantly."""
    calls: list[float] = []

    async def fake_async_sleep(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr("tfl.client.time.sleep", calls.append)
    monkeypatch.setattr("tfl.client.asyncio.sleep", fake_async_sleep)
    return calls


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(api: respx.MockRouter) -> Iterator[TflClient]:
    with TflClient(app_key="test-key") as c:
        yield c


@pytest.fixture
async def aclient(api: respx.MockRouter) -> AsyncIterator[AsyncTflClient]:
    async with AsyncTflClient(app_key="test-key") as c:
        yield c

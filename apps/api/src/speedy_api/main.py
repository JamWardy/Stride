"""HTTP layer over tfl-walk: catchable trains near a point, and a station picker.

Run with ``uv run uvicorn speedy_api.main:app --reload``. Set ``TFL_APP_KEY`` for a higher
TfL rate limit; it is only ever read here, never sent to the browser. ``CORS_ORIGINS`` is
a comma-separated list of allowed frontend origins (default: the Vite dev server).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tfl import AsyncTflClient, TflError
from tfl_walk import AsyncWalkPlanner, Risk, WalkerProfile, WalkOption

#: Seconds live arrivals are shared between requests.
ARRIVALS_TTL_S = 20.0
#: Seconds station searches are cached (stations don't move).
SEARCH_TTL_S = 300.0
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)

router = APIRouter()


class Station(BaseModel):
    """A station the user can pick as their starting point."""

    id: str
    name: str
    lat: float
    lon: float


def get_client(request: Request) -> AsyncTflClient:
    """Return the app's shared TfL client (overridden in tests)."""
    client: AsyncTflClient = request.app.state.tfl
    return client


Client = Annotated[AsyncTflClient, Depends(get_client)]


@router.get("/options")
async def options(
    client: Client,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    speed_kmh: Annotated[float, Query(gt=0, le=15, description="Walking speed")] = 5.5,
    max_walk: Annotated[float, Query(gt=0, le=30, description="Longest walk, minutes")] = 12,
    risk: Risk = "medium",
) -> list[WalkOption]:
    """Trains the walker can still catch from ``lat``/``lon``, soonest first."""
    planner = AsyncWalkPlanner(client, WalkerProfile(walking_speed_kmh=speed_kmh, risk=risk))
    return await planner.options_from(lat, lon, max_walk)


@router.get("/stations/search")
async def search_stations(
    client: Client, q: Annotated[str, Query(min_length=1, max_length=100)]
) -> list[Station]:
    """Stations matching ``q``, best match first."""
    stops = await client.stops.search(q)
    return [Station(id=s.id, name=s.name, lat=s.lat, lon=s.lon) for s in stops]


async def _tfl_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"TfL request failed: {exc}"})


def create_app(
    *,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
    arrivals_ttl_s: float = ARRIVALS_TTL_S,
) -> FastAPI:
    """Build the app with one shared TfL client for its lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncTflClient(
            cache_ttl=SEARCH_TTL_S, arrivals_cache_ttl=arrivals_ttl_s
        ) as client:
            app.state.tfl = client
            yield

    app = FastAPI(title="speedy-tfl", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["GET"])
    app.add_exception_handler(TflError, _tfl_error)
    app.include_router(router)
    return app


def _cors_origins_from_env() -> tuple[str, ...]:
    raw = os.environ.get("CORS_ORIGINS")
    if not raw:
        return DEFAULT_CORS_ORIGINS
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


app = create_app(cors_origins=_cors_origins_from_env())

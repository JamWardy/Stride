"""HTTP layer over tfl-walk: door-to-door journeys at the walker's own pace.

Run with ``uv run uvicorn stride_api.main:app --reload``. Set ``TFL_APP_KEY`` for a higher
TfL rate limit and ``GOOGLE_MAPS_API_KEY`` for place suggestions; both are only ever read
here, never sent to the browser. ``CORS_ORIGINS`` is
a comma-separated list of allowed frontend origins (default: the Vite dev server).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from tfl import (
    AsyncTflClient,
    LocationOption,
    TflAmbiguousLocationError,
    TflError,
    TflNotFoundError,
)
from tfl_walk import AsyncJourneyPlanner, JourneyOption, Risk, WalkerProfile

from .places import GooglePlaces, PlacesError

#: Seconds live arrivals are shared between requests.
ARRIVALS_TTL_S = 20.0
#: Seconds slow-changing data (route sequences) is cached.
CACHE_TTL_S = 300.0
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
#: TfL modes whose stations are offered first in place suggestions.
STATION_MODES = ("tube", "dlr", "overground", "elizabeth-line")
MAX_STATIONS = 3

router = APIRouter()


class JourneysFound(BaseModel):
    """Ways to get there, earliest arrival first; empty when TfL finds no route."""

    kind: Literal["journeys"] = "journeys"
    journeys: list[JourneyOption]


class PlaceChoice(BaseModel):
    """One of TfL's candidates for an ambiguous place. Send ``value`` back as from/to."""

    value: str
    name: str
    place_type: str | None


class AmbiguousPlaces(BaseModel):
    """TfL couldn't tell which place was meant; pick one per non-empty list and ask again."""

    kind: Literal["ambiguous"] = "ambiguous"
    from_options: list[PlaceChoice]
    to_options: list[PlaceChoice]


JourneysResponse = Annotated[JourneysFound | AmbiguousPlaces, Field(discriminator="kind")]


def _choices(options: Sequence[LocationOption]) -> list[PlaceChoice]:
    return [
        PlaceChoice(value=o.parameter_value, name=o.place.name, place_type=o.place.place_type)
        for o in options
    ]


class StationSuggestion(BaseModel):
    """A TfL station; ``value`` can be sent straight to ``/journeys``."""

    kind: Literal["station"] = "station"
    name: str
    value: str


class PlaceSuggestion(BaseModel):
    """A Google place; resolve ``place_id`` with ``/places/{place_id}`` to get its value."""

    kind: Literal["place"] = "place"
    name: str
    detail: str | None
    place_id: str


Suggestion = Annotated[StationSuggestion | PlaceSuggestion, Field(discriminator="kind")]


class ResolvedPlace(BaseModel):
    """A chosen place as ``"lat,lon"``, ready for ``/journeys``."""

    value: str


def get_places(request: Request) -> GooglePlaces | None:
    """Return the Google Places client, or ``None`` when no API key is set."""
    places: GooglePlaces | None = request.app.state.places
    return places


Places = Annotated[GooglePlaces | None, Depends(get_places)]


def get_client(request: Request) -> AsyncTflClient:
    """Return the app's shared TfL client (overridden in tests)."""
    client: AsyncTflClient = request.app.state.tfl
    return client


Client = Annotated[AsyncTflClient, Depends(get_client)]


@router.get("/journeys")
async def journeys(
    client: Client,
    from_: Annotated[
        str,
        Query(alias="from", min_length=1, max_length=200, description='"lat,lon" or a place'),
    ],
    to: Annotated[str, Query(min_length=1, max_length=200, description='"lat,lon" or a place')],
    speed_kmh: Annotated[float, Query(gt=0, le=15, description="Walking speed")] = 5.5,
    risk: Risk = "medium",
) -> JourneysResponse:
    """Ways to get from ``from`` to ``to`` leaving now, timed at the walker's pace."""
    planner = AsyncJourneyPlanner(client, WalkerProfile(walking_speed_kmh=speed_kmh, risk=risk))
    try:
        return JourneysFound(journeys=await planner.journeys(from_, to))
    except TflAmbiguousLocationError as exc:
        return AmbiguousPlaces(
            from_options=_choices(exc.from_options), to_options=_choices(exc.to_options)
        )
    except TflNotFoundError:  # TfL's "no journey found"
        return JourneysFound(journeys=[])


@router.get("/places")
async def suggest_places(
    client: Client,
    places: Places,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    session: Annotated[
        str,
        Query(min_length=1, max_length=64, description="One token per search, from the browser"),
    ],
) -> list[Suggestion]:
    """Stations first, then Google's places, for type-ahead in the From and To boxes."""
    stations = await client.stops.search(q, modes=STATION_MODES)
    suggestions: list[StationSuggestion | PlaceSuggestion] = [
        StationSuggestion(name=s.name, value=s.ics_id or s.id) for s in stations[:MAX_STATIONS]
    ]
    if places is not None:
        suggestions += [
            PlaceSuggestion(name=p.name, detail=p.detail, place_id=p.place_id)
            for p in await places.autocomplete(q, session)
        ]
    return suggestions


@router.get("/places/{place_id}")
async def resolve_place(
    places: Places,
    place_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,300}$")],
    session: Annotated[str, Query(min_length=1, max_length=64)],
) -> ResolvedPlace:
    """Return the chosen place as ``"lat,lon"``, ending the Google autocomplete session."""
    if places is None:
        raise HTTPException(status_code=503, detail="Place search is not configured")
    lat, lon = await places.location(place_id, session)
    return ResolvedPlace(value=f"{lat},{lon}")


async def _places_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


async def _tfl_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"TfL request failed: {exc}"})


def create_app(
    *,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
    arrivals_ttl_s: float = ARRIVALS_TTL_S,
    google_api_key: str | None = None,
) -> FastAPI:
    """Build the app with one shared TfL client for its lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with (
            AsyncTflClient(cache_ttl=CACHE_TTL_S, arrivals_cache_ttl=arrivals_ttl_s) as client,
            httpx.AsyncClient(timeout=10.0) as http,
        ):
            app.state.tfl = client
            app.state.places = GooglePlaces(google_api_key, http) if google_api_key else None
            yield

    app = FastAPI(title="Stride", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["GET"])
    app.add_exception_handler(TflError, _tfl_error)
    app.add_exception_handler(PlacesError, _places_error)
    app.include_router(router)
    return app


def _cors_origins_from_env() -> tuple[str, ...]:
    raw = os.environ.get("CORS_ORIGINS")
    if not raw:
        return DEFAULT_CORS_ORIGINS
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


app = create_app(
    cors_origins=_cors_origins_from_env(),
    google_api_key=os.environ.get("GOOGLE_MAPS_API_KEY") or None,
)

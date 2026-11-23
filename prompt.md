# Project: Python TfL SDK + "walk or wait" library

## Goal
Build two Python packages in one repo:

1. **`tfl-sdk`** – a clean, well-designed, typed Python SDK for the TfL Unified API (https://api.tfl.gov.uk). It must be fully general-purpose and know nothing about walking speed.
2. **`tfl-walk`** – a library built ON TOP of `tfl-sdk` that answers: "Given where I am and how fast I walk, should I wait at the nearest station, walk to a different station to catch a train there, or just walk?"

Plus a small CLI demo (`examples/cli.py`) that uses both.

`tfl-walk` must depend on `tfl-sdk` only through its public API, exactly like a third-party user would. No walking/routing logic in the SDK.

## Why this exists
Existing Python TfL clients are either thin/outdated (`tflunifiedapi`, depends on deprecated msrest) or auto-generated from the OpenAPI spec with unergonomic method names (`pydantic-tfl-api`, e.g. `GetByModeByPathModes`). This SDK should be hand-designed for readability: `client.stops.arrivals(stop_id)`, not generated operation IDs. Do NOT depend on those packages; call the API directly.

## Tech stack
- Python 3.11+
- `uv` workspace with two packages: `packages/tfl-sdk` (import name `tfl`) and `packages/tfl-walk` (import name `tfl_walk`)
- `httpx` (sync + async), `pydantic` v2 for models
- `pytest`, `respx` for mocking HTTP; tests must NOT hit the real API
- `ruff` for lint/format, `mypy --strict` (or pyright) clean
- `src/` layout, `py.typed` marker

## Part 1 – `tfl-sdk`

### Client
- `TflClient(app_key: str | None = None, timeout=10.0, max_retries=3)`; if `app_key` is None, read `TFL_APP_KEY` from env. Key is sent as the `app_key` query param.
- `AsyncTflClient` with the same interface (share as much code as possible; don't duplicate logic).
- Usable as a context manager.
- Resource-style namespaces: `client.stops`, `client.lines`, `client.journeys`.

### Methods (v1 scope)
- `client.stops.search(query: str, modes=("tube",)) -> list[StopSummary]` → `/StopPoint/Search/{query}`
- `client.stops.nearby(lat, lon, radius_m=800, stop_types=("NaptanMetroStation",)) -> list[NearbyStop]` → `/StopPoint?lat=&lon=&radius=&stopTypes=` (include distance in metres)
- `client.stops.get(stop_id) -> Stop` → `/StopPoint/{id}`
- `client.stops.arrivals(stop_id) -> list[Arrival]` → `/StopPoint/{id}/Arrivals`, **sorted by time to station**
- `client.lines.status(modes=("tube",)) -> list[LineStatus]` → `/Line/Mode/{modes}/Status`
- `client.lines.disruptions(line_id) -> list[Disruption]` → `/Line/{id}/Disruption`
- `client.journeys.plan(from_, to, *, depart_at=None) -> list[Journey]` → `/Journey/JourneyResults/{from}/to/{to}` (handle the 300 "disambiguation" response by raising a clear `TflAmbiguousLocationError` containing the options)

Before writing models, call each endpoint once against the real API (I'll provide a key via `TFL_APP_KEY`), save the raw JSON responses under `tests/fixtures/`, and design models from the real shapes. Do not invent fields.

### Models
- Pydantic models with clean snake_case names; strip TfL noise like `$type`.
- Parse timestamps into timezone-aware `datetime`.
- `Arrival` should expose at least: `line_id`, `line_name`, `platform_name`, `direction`, `destination_name`, `expected_arrival`, `time_to_station` (seconds) and a `minutes_away` convenience property.
- Be tolerant of missing/optional fields (TfL data is inconsistent); ignore unknown fields.

### Errors
`TflError` base; subclasses `TflAuthError` (401/403), `TflNotFoundError` (404), `TflRateLimitError` (429), `TflServerError` (5xx), `TflAmbiguousLocationError` (300 from journey planner). Include status code and response body.

### Reliability
- Retries with exponential backoff + jitter on timeouts, 429, and 5xx (respect `Retry-After` if present). No retries on 4xx other than 429.
- Optional simple in-memory TTL cache, off by default, enable-able per client, intended for slow-changing data (`stops.get`, `stops.search`). Never cache arrivals.

### Docs
- README with a 30-second quickstart, an example per method, and a note that it's unofficial and not affiliated with TfL.
- Docstrings on all public methods.

## Part 2 – `tfl-walk`

### Public API
```python
from tfl import TflClient
from tfl_walk import WalkPlanner, WalkerProfile

planner = WalkPlanner(client, WalkerProfile(walking_speed_kmh=5.5))
options = planner.options_from(lat=51.515, lon=-0.141, max_walk_minutes=12)
for opt in options:
    print(
        opt.station_name,
        opt.line_name,
        opt.walk_minutes,
        opt.wait_minutes,
        opt.can_make_it,
        opt.margin_seconds,
    )
```

### Logic (v1)
1. Find stations within `max_walk_minutes` at the user's walking speed (use `stops.nearby` with radius derived from speed × time).
2. Estimate walking time to each station: haversine distance × detour factor (default 1.3, configurable) ÷ walking speed.
3. Add a per-station "street to platform" buffer (default 2 minutes, overridable via a dict of station id → seconds).
4. Fetch live arrivals for each station (concurrently in the async version).
5. For each arrival, the user can catch it if `walk_time + entry_buffer + safety_margin <= time_to_station`. `safety_margin` comes from a `risk` setting: `"low"` = 90s, `"medium"` = 45s, `"high"` = 0s.
6. Return `WalkOption` objects ford catchable trains: station, line, direction/destination, platform, walk time, wait time on platform, departure time, margin. Sort by departure time, and group or dedupe so the output shows meaningfully different options (e.g. best option per line+direction per station).

Keep the logic pure and testable: separate "fetch data" from "compute options" so the computation can be unit-tested with plain data and no HTTP mocking.

Leave clear extension points (but don't implement yet) for: real street routing (OSRM/OpenRouteService), pulling pace from Strava, and filtering to options heading toward a destination.

## Part 3 – CLI demo
`examples/cli.py` using `argparse`: `--lat --lon --speed --max-walk --risk`. Prints a readable table of options. Also accept `--station "Oxford Circus"` as an alternative to lat/lon (resolve via `stops.search`).

## Testing
- SDK: tests for every method using recorded fixtures + `respx`; tests for retry behaviour, error mapping, cache TTL, the 300 disambiguation case.
- tfl-walk: unit tests for walk-time maths, catchability, risk margins, sorting/deduping, using hand-built data.
- Aim for high coverage on logic; don't chase 100% on glue code.

## Working style
- Work in this order: SDK client + errors + retries → stops methods → lines/journeys → tfl-walk core logic → CLI. Commit after each step with a clear message.
- Stop and check with me after the SDK core (client + stops methods + tests) is done, before starting tfl-walk.
- If the real API response shape contradicts anything in this brief, follow the real API and tell me what differed.
- Don't add features beyond this scope without asking; list ideas in a `ROADMAP.md` instead.
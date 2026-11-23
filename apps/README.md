# Web app

A phone-first page showing the trains you can still catch on foot. It has two parts:

| Part | What | Stack |
|---|---|---|
| `apps/api` | Thin HTTP layer over `tfl-walk` | FastAPI |
| `apps/web` | The page | Vite + React + TypeScript |

## Run it

```bash
make install   # uv sync + npm install
make dev       # API on :8000, web on :5173; Ctrl-C stops both
```

Open http://localhost:5173.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /options?lat=&lon=&speed_kmh=5.5&max_walk=12&risk=medium` | Catchable trains, soonest first |
| `GET /stations/search?q=` | Stations for the picker |

Arrivals are shared between requests for 20 s, and station searches for 5 min.

## Settings

| Variable | Where | Default |
|---|---|---|
| `TFL_APP_KEY` | API (never sent to the browser) | anonymous |
| `CORS_ORIGINS` | API, comma-separated | `http://localhost:5173` |
| `VITE_API_URL` | Web | `http://localhost:8000` |

## Other commands

- `make types` regenerates `apps/web/src/api/schema.d.ts` from FastAPI's OpenAPI schema. Run it after changing an API response.
- `make test` runs the Python and frontend tests.
- `make lint` runs ruff, mypy and tsc.

# Web app

A phone-first, door-to-door journey planner timed at your own walking speed. It has two parts:

| Part | What | Stack |
|---|---|---|
| `apps/api` | Thin HTTP layer over `tfl-walk` | FastAPI |
| `apps/web` | The page | Vite + React + TypeScript |

## Run it

```bash
just install   # uv sync + npm install
just dev       # API on :8000, web on :5173; Ctrl-C stops both
```

Open http://localhost:5173.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /journeys?from=&to=&speed_kmh=5.5&risk=medium` | `kind: "journeys"` with routes, earliest arrival first; or `kind: "ambiguous"` with TfL's candidate places |
| `GET /places?q=&session=` | Type-ahead: up to 3 TfL stations, then Google's places |
| `GET /places/{place_id}?session=` | A Google place as `"lat,lon"`; ends the Google session |

`from`/`to` take `"lat,lon"`, a postcode, a place name, or a candidate's `value`. Live arrivals are shared between requests for 20 s.

## Settings

| Variable | Where | Default |
|---|---|---|
| `TFL_APP_KEY` | API (never sent to the browser) | anonymous |
| `GOOGLE_MAPS_API_KEY` | API (never sent to the browser); Places API (New) | unset: stations only |
| `CORS_ORIGINS` | API, comma-separated | `http://localhost:5173` |
| `VITE_API_URL` | Web | `http://localhost:8000` |

## Other commands

- `just types` regenerates `apps/web/src/api/schema.d.ts` from FastAPI's OpenAPI schema. Run it after changing an API response.
- `just test` runs the Python and frontend tests.
- `just lint` runs ruff, mypy and tsc.

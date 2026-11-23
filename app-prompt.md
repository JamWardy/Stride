## Part 4 – Web app (after Parts 1–3 are done and reviewed)

### Backend: `apps/api` (FastAPI)
- Thin HTTP layer over `tfl-walk`; no TfL or walking logic here.
- `GET /options?lat=&lon=&speed_kmh=&max_walk=&risk=` → JSON list of WalkOptions
- `GET /stations/search?q=` → for the station-picker
- Uses `AsyncTflClient`; short server-side cache (~20s) on arrivals to stay well under TfL rate limits.
- CORS configured for the frontend's dev origin. API key stays server-side only.

### Frontend: `apps/web` (TypeScript, Vite + React)
- Mobile-first: I'll mainly use this on my phone while standing outside.
- "Use my location" button (browser geolocation) + fallback station search.
- Walking speed slider (km/h, remembered in localStorage) and a risk toggle (low/medium/high).
- Results as cards: station, line (in official line colour), walk time, wait on platform, departure time, and a clear "comfortable / tight / risky" badge based on margin.
- Auto-refresh every 30s while the page is open, with a visible "updated Xs ago".
- Types for the API responses generated from FastAPI's OpenAPI schema (e.g. `openapi-typescript`), not hand-written.
- Keep styling simple (plain CSS or Tailwind); no component library needed.

### Dev
- One command to run both (e.g. a `Makefile` or `justfile` target).
- Basic tests: API endpoint tests with tfl-walk mocked; a couple of frontend component tests.
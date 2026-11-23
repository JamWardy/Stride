## Part 4 – Web app: door-to-door journeys at my walking speed

### Goal
"I want to go to X": show the routes I can take from where I am, timed at my own walking speed, including walking outside and inside stations. Like Google Maps or Citymapper, but with an adjustable walking speed. This is not a "trains near me" list.

### Scope
- Modes: Tube, DLR, Overground, Elizabeth line, plus walking. No buses.
- Destination: any place TfL's journey planner accepts (stations, postcodes, addresses, place names). When a name is ambiguous, show TfL's candidates and let me pick one.
- Start: my location (browser geolocation), or a place picked the same way as the destination.

### SDK: `tfl-sdk` (fix gaps here; never bypass the SDK)
- Done: `journeys.plan(..., modes=, walking_speed=)`; `Leg.distance_m` (walking legs), `Leg.path.stops`, `Instruction.steps`; opt-in `arrivals_cache_ttl`, where cached `time_to_station` is reduced by the entry's age.
- To do: `lines.route_sequence(line_id, direction)` → `/Line/{id}/Route/Sequence/{direction}`, with models designed from recorded real responses. This tells whether a live train calls at the stop where I get off, across branches.

### Library: `tfl-walk` – `JourneyPlanner`
Pure logic, kept separate from fetching like the existing planner. For each TfL route:
1. **Street walks:** distance in metres ÷ my speed × detour factor.
2. **Changing trains:** use TfL's own allowance. The smallest gap at a station across TfL's returned journeys is the change time, scaled by my speed relative to TfL's walking-speed setting.
3. **Street to platform:** take it from TfL's first and last walk legs (TfL's duration minus the street walk at TfL's pace). First, estimate TfL's pace for slow, average and fast from recorded walk legs, and keep that data as fixtures.
4. **First train:** live arrivals at the boarding station, on the right line, calling at my alighting stop (route sequence). Use the existing catchable rule: walk + entry + safety margin ≤ time to station.
5. **Each change:** the next live train I can reach at that station. Fall back to TfL's timetabled time once live arrivals don't reach far enough ahead.
6. **Output per route:** leave-by time, arrival time, the legs with each train to aim for, and the smallest margin across all connections.
- Per-station overrides for street-to-platform and change times.

### Backend: `apps/api` (FastAPI)
- Thin HTTP layer over `tfl-walk`; no TfL or walking logic here.
- `GET /journeys?from=&to=&speed_kmh=&risk=` → routes, or TfL's candidates when `from` or `to` is ambiguous.
- `AsyncTflClient` with `arrivals_cache_ttl≈20` to stay well under TfL rate limits.
- CORS for the frontend's dev origin. API key stays server-side only.

### Frontend: `apps/web` (TypeScript, Vite + React)
- Mobile-first: I'll mainly use this on my phone while standing outside.
- "Where to?" input, with a candidate picker for ambiguous names. "Use my location", or a typed start.
- Walking speed slider (km/h, remembered in localStorage) and a risk toggle (low/medium/high).
- Route cards: leave-by time, arrival time, each leg (walk, then line in its official colour with the train to catch, then change), and a "comfortable / tight / risky" badge from the route's smallest margin.
- Auto-refresh every 30 s while the page is open, with a visible "updated Xs ago".
- API response types generated from FastAPI's OpenAPI schema (`openapi-typescript`), not hand-written.
- Simple styling (plain CSS); no component library.

### Dev
- One command runs both (`just dev`).
- Tests: tfl-walk journey maths with hand-built data; SDK methods with recorded fixtures; API endpoint tests with tfl-walk mocked; a few frontend component tests.

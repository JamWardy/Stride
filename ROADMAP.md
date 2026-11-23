# Roadmap (ideas, not in scope yet)

- `stops.nearby`: pagination (`page` param) and a `modes` filter.
- Dedicated `TflTimeoutError` instead of a plain `TflError` when retries on timeouts run out.
- Helper to resolve hub ids (e.g. `HUBBAN`) to their child stations, which carry the arrivals.
- Trains that skip stops (e.g. Metropolitan fast trains): `lines.route_sequence` lists every stop on each route, so a fast train can look as if it calls at a station it passes through. Options: check the train also appears in the alighting station's arrivals by `vehicle_id` (works for Tube and Elizabeth line; DLR has no ids, Metropolitan ids look reused), or add `lines.timetable` (`/Line/{id}/Timetable/{from}/to/{to}`) for real stopping patterns.

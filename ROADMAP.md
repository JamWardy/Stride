# Roadmap (ideas, not in scope yet)

- `stops.nearby`: pagination (`page` param) and a `modes` filter.
- Dedicated `TflTimeoutError` instead of a plain `TflError` when retries on timeouts run out.
- Helper to resolve hub ids (e.g. `HUBBAN`) to their child stations, which carry the arrivals.
- Cap on honoured `Retry-After` so a large value can't stall a caller.

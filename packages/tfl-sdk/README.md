# tfl-sdk

A typed, hand-designed Python client for the [TfL Unified API](https://api.tfl.gov.uk).

> **Unofficial.** This project is not affiliated with or endorsed by Transport for London.

## 30-second quickstart

```bash
uv add tfl-sdk          # or: pip install tfl-sdk
export TFL_APP_KEY=...  # optional; anonymous calls work at a lower rate limit
```

```python
from tfl import TflClient

with TflClient() as client:
    for a in client.stops.arrivals("940GZZLUOXC")[:5]:
        print(f"{a.line_name:10} {a.destination_name or '':40} {a.minutes_away} min")
```

Async: use `AsyncTflClient` with `async with` and `await` — same methods.

## Methods

| Method | Endpoint |
|---|---|
| `stops.search(query, modes=("tube",))` | `/StopPoint/Search/{query}` |
| `stops.nearby(lat, lon, radius_m=800, stop_types=("NaptanMetroStation",))` | `/StopPoint?lat&lon` |
| `stops.get(stop_id)` | `/StopPoint/{id}` |
| `stops.arrivals(stop_id)` | `/StopPoint/{id}/Arrivals` |

```python
client.stops.search("Oxford Circus")[0].id  # '940GZZLUOXC'
[s.name for s in client.stops.nearby(51.515, -0.141)]  # each has .distance_m
[l.name for l in client.stops.get("940GZZLUOXC").lines]  # ['Bakerloo', 'Central', 'Victoria']
client.stops.arrivals("940GZZLUOXC")[0].minutes_away  # sorted soonest first
```

## Options

```python
TflClient(app_key=None, timeout=10.0, max_retries=3, cache_ttl=None)
```

- **Retries:** timeouts, connection errors, 429 and 5xx, with exponential backoff and jitter; honours `Retry-After` up to 8 s (longer waits raise `TflRateLimitError` with `.retry_after`).
- **Cache:** set `cache_ttl` (seconds) to cache `stops.get` and `stops.search`. Arrivals are never cached.

## Errors

All inherit `TflError` (with `.status_code`, `.body`, `.url`):
`TflAuthError` (401/403), `TflNotFoundError` (404), `TflRateLimitError` (429), `TflServerError` (5xx).

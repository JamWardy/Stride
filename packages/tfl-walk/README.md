# tfl-walk

Walk or wait? Given where you are and how fast you walk, find the London trains you can still catch on foot. Built on [`tfl-sdk`](../tfl-sdk), using only its public API.

## Quickstart

```python
from tfl import TflClient
from tfl_walk import WalkPlanner, WalkerProfile

with TflClient() as client:
    planner = WalkPlanner(client, WalkerProfile(walking_speed_kmh=5.5, risk="medium"))
    for opt in planner.options_from(lat=51.515, lon=-0.141, max_walk_minutes=12):
        print(opt.station_name, opt.line_name, round(opt.walk_minutes), round(opt.wait_minutes))
```

Async: `AsyncWalkPlanner` with an `AsyncTflClient`; it fetches stations' arrivals concurrently.

## How it decides

| Step | Rule |
|---|---|
| Stations | `stops.nearby` within speed × `max_walk_minutes` |
| Walk time | straight-line distance × 1.3 detour ÷ speed |
| Entry buffer | 2 min street-to-platform (override per station with `entry_buffers`) |
| Catchable | walk + buffer + safety margin ≤ train's time to station |
| Safety margin | `risk`: low 90 s, medium 45 s, high 0 s |
| Output | earliest catchable train per station, line and direction, soonest first |

Each `WalkOption` has `walk_minutes`, `wait_minutes` (time on the platform), `margin_seconds` (slack beyond the safety margin), `departure_time` and `can_make_it`.

## Options

```python
WalkPlanner(
    client,
    profile,
    walk_estimator=StraightLineWalk(detour_factor=1.3),
    entry_buffer_s=120,
    entry_buffers={"940GZZLUOXC": 180},
)
```

For street routing, pass any object with a `walk_seconds(from_lat, from_lon, to_lat, to_lon, speed_m_s)` method as `walk_estimator`.

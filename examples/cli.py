"""Walk or wait? List the trains you can still catch on foot from where you are.

Examples:
    uv run python examples/cli.py --lat 51.515 --lon -0.141
    uv run python examples/cli.py --station "Oxford Circus" --speed 6 --risk low

Set ``TFL_APP_KEY`` for a higher rate limit; anonymous requests also work.

"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from tfl import TflClient, TflError
from tfl_walk import SAFETY_MARGIN_S, WalkerProfile, WalkOption, WalkPlanner

LONDON = ZoneInfo("Europe/London")
HEADERS = ("Departs", "Station", "Line", "Towards", "Platform", "Walk", "Wait", "Margin")
#: Dropped from names to keep the table narrow. Other suffixes (" DLR Station") are kept:
#: they tell apart stations that share a name, e.g. Bank's Underground and DLR stations.
TUBE_SUFFIX = " Underground Station"


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        description="List the London trains you can still catch on foot.",
    )
    parser.add_argument("--lat", type=float, help="your latitude (use with --lon)")
    parser.add_argument("--lon", type=float, help="your longitude (use with --lat)")
    parser.add_argument(
        "--station", help='start from a station instead of --lat/--lon, e.g. "Oxford Circus"'
    )
    parser.add_argument(
        "--speed", type=float, default=5.5, help="walking speed in km/h (default: 5.5)"
    )
    parser.add_argument(
        "--max-walk",
        type=float,
        default=12,
        help="longest walk to a station, in minutes (default: 12)",
    )
    parser.add_argument(
        "--risk",
        choices=list(SAFETY_MARGIN_S),
        default="medium",
        help="safety margin: low = 90 s, medium = 45 s, high = 0 s (default: medium)",
    )
    return parser


def resolve_location(
    client: TflClient, parser: argparse.ArgumentParser, args: argparse.Namespace
) -> tuple[float, float, str]:
    """Return ``(lat, lon, label)`` from either ``--station`` or ``--lat``/``--lon``."""
    has_coords = args.lat is not None or args.lon is not None
    if args.station and has_coords:
        parser.error("use either --station or --lat/--lon, not both")
    if args.station:
        matches = client.stops.search(args.station)
        if not matches:
            parser.error(f"no tube station found matching {args.station!r}")
        stop = matches[0]
        return stop.lat, stop.lon, short_name(stop.name)
    if args.lat is None or args.lon is None:
        parser.error("give --lat and --lon together, or --station")
    return args.lat, args.lon, f"{args.lat}, {args.lon}"


def _minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min"


def short_name(name: str) -> str:
    """Drop the tube suffix, e.g. "Bank Underground Station" -> "Bank"."""
    return name.removesuffix(TUBE_SUFFIX)


def format_table(options: Sequence[WalkOption]) -> str:
    """Render options as an aligned plain-text table."""
    rows = [
        (
            o.departure_time.astimezone(LONDON).strftime("%H:%M"),
            short_name(o.station_name),
            o.line_name,
            short_name(o.destination_name or o.direction or ""),
            o.platform_name or "",
            _minutes(o.walk_seconds),
            _minutes(o.wait_seconds),
            _minutes(o.margin_seconds),
        )
        for o in options
    ]
    widths = [max(len(row[i]) for row in (HEADERS, *rows)) for i in range(len(HEADERS))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)) for row in rows]
    header = "  ".join(h.ljust(w) for h, w in zip(HEADERS, widths, strict=True))
    rule = "  ".join("-" * w for w in widths)
    return "\n".join(line.rstrip() for line in (header, rule, *lines))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        profile = WalkerProfile(walking_speed_kmh=args.speed, risk=args.risk)
    except ValueError as exc:
        parser.error(str(exc))
    if args.max_walk <= 0:
        parser.error("--max-walk must be positive")

    try:
        with TflClient() as client:
            lat, lon, label = resolve_location(client, parser, args)
            options = WalkPlanner(client, profile).options_from(lat, lon, args.max_walk)
    except TflError as exc:
        print(f"TfL request failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"From {label}, walking at {args.speed:g} km/h, up to {args.max_walk:g} min, "
        f"{args.risk} risk:\n"
    )
    if not options:
        print("No catchable trains right now. Try a longer --max-walk or a higher --risk.")
    else:
        print(format_table(options))
    return 0


if __name__ == "__main__":
    sys.exit(main())

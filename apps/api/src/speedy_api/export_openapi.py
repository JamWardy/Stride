"""Write the API's OpenAPI schema as JSON, for generating the frontend's types.

Usage: ``uv run python -m speedy_api.export_openapi apps/web/openapi.json``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import create_app


def main(argv: list[str]) -> int:
    """Write the schema to the path in ``argv[0]``, or to stdout without one."""
    text = json.dumps(create_app().openapi(), indent=2) + "\n"
    if argv:
        Path(argv[0]).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Helpers shared by the SDK tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://api.tfl.gov.uk"


def load(name: str) -> Any:
    """Load a recorded real TfL response from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text())

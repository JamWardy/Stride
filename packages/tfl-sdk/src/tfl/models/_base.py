"""Base model and field types shared by all TfL models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

#: TfL returns some timestamps without an offset (e.g. journey times); they are London local.
LONDON = ZoneInfo("Europe/London")


class TflModel(BaseModel):
    """Base for all models: snake_case attributes, camelCase JSON, unknown fields ignored.

    TfL's ``$type`` noise is dropped because it is not a declared field.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
    )


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=LONDON)
    return value


def _parse_optional_datetime(value: Any) -> Any:
    if value in (None, ""):
        return None
    parsed = _parse_datetime(value)
    # TfL uses 0001-01-01T00:00:00 as a "not set" sentinel.
    if isinstance(parsed, datetime) and parsed.year == 1:
        return None
    return parsed


def _empty_to_none(value: Any) -> Any:
    return None if value == "" else value


#: Timezone-aware datetime. Offset-less values are interpreted as Europe/London.
TflDatetime = Annotated[datetime, BeforeValidator(_parse_datetime)]
#: Like :data:`TflDatetime`, but missing values and TfL's ``0001-01-01`` sentinel become None.
OptionalTflDatetime = Annotated[datetime | None, BeforeValidator(_parse_optional_datetime)]
#: Optional string where TfL's empty string ``""`` becomes None.
OptionalStr = Annotated[str | None, BeforeValidator(_empty_to_none)]

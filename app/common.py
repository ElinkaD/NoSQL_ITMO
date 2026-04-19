import re
from datetime import date, datetime
from typing import Callable, TypeVar

from bson import ObjectId

# валидация входных данных
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
ALLOWED_EVENT_CATEGORIES = {"meetup", "concert", "exhibition", "party", "other"}
T = TypeVar("T")


def is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def parse_rfc3339(value: str) -> datetime | None:
    if not RFC3339_PATTERN.fullmatch(value):
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo is not None else None


def parse_uint_parameter(value: str | None) -> int | None:
    if value is None:
        return None
    if not value.isdigit():
        return None
    return int(value)


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None or not ObjectId.is_valid(value):
        return None
    return ObjectId(value)


def parse_yyyymmdd(value: str | None) -> date | None:
    if value is None:
        return None
    if len(value) != 8 or not value.isdigit():
        return None

    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def is_valid_event_category(value: object) -> bool:
    return isinstance(value, str) and value in ALLOWED_EVENT_CATEGORIES


def parse_non_empty_string_parameter(value: str | None) -> str | None:
    if value is None:
        return None
    if not is_non_empty_string(value):
        return None
    return value


def parse_optional_parameter(value: str | None, parser: Callable[[str | None], T | None]) -> tuple[T | None, bool]:
    parsed_value = parser(value)
    return parsed_value, value is not None and parsed_value is None

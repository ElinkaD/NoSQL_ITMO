import re
from datetime import datetime

# валидация входных данных 
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


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

import re
from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser

BOOLEAN_FIELDS = {"approved", "is_completed"}
INTEGER_BOUNDS = {
    "frame_count": (2, 12),
    "duration_ms": (40, 2000),
    "loop_count": (0, 65535),
    "quantity": (1, 2_147_483_647),
}
DECIMAL_FIELDS = {"unit_cost"}
DATETIME_FIELDS = {
    "submitted_at",
    "scheduled_publish_at",
    "released_at",
    "purchased_at",
    "expires_at",
    "distributed_at",
}
INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")


def _parse_boolean(key: str, value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ParseError({key: "必须提交 JSON 布尔值 true 或 false。"})


def _parse_integer(key: str, value):
    if isinstance(value, bool):
        raise ParseError({key: "必须是整数。"})
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        parsed = int(value.strip())
    else:
        raise ParseError({key: "必须是整数。"})

    minimum, maximum = INTEGER_BOUNDS[key]
    if parsed < minimum or parsed > maximum:
        raise ParseError({key: f"必须在 {minimum} 到 {maximum} 之间。"})
    return parsed


def _parse_decimal(key: str, value):
    if isinstance(value, bool):
        raise ParseError({key: "必须是非负金额。"})
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ParseError({key: "必须是有效金额。"}) from exc
    if parsed < 0 or parsed > Decimal("99999999.99"):
        raise ParseError({key: "金额超出允许范围。"})
    return parsed


def _validate_datetime(key: str, value):
    if value in {None, ""}:
        return value
    if not isinstance(value, str) or parse_datetime(value) is None:
        raise ParseError({key: "必须是带时区的 ISO 8601 日期时间。"})
    return value


def _normalize(value, key: str | None = None):
    if isinstance(value, dict):
        return {
            child_key: _normalize(child_value, child_key)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_normalize(item, key) for item in value]
    if key in BOOLEAN_FIELDS:
        return _parse_boolean(key, value)
    if key in INTEGER_BOUNDS:
        return _parse_integer(key, value)
    if key in DECIMAL_FIELDS:
        return _parse_decimal(key, value)
    if key in DATETIME_FIELDS:
        return _validate_datetime(key, value)
    return value


class StrictJSONParser(JSONParser):
    """Normalize and validate shared write-request scalar types before views run."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type=media_type, parser_context=parser_context)
        return _normalize(data)

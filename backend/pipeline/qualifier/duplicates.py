from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent, QualityFlag, Severity

DEFAULT_FIELDS: tuple[str, ...] = (
    "subject_id",
    "category",
    "timestamp",
    "payload.value",
)
DEFAULT_VALUE_ROUND_DIGITS = 3


def _resolve(event: CanonicalEvent, path: str) -> Any:
    parts = path.split(".")
    obj: Any = event
    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
    return obj


def _fingerprint(
    event: CanonicalEvent,
    fields: tuple[str, ...],
    round_digits: int,
) -> tuple:
    parts: list[Any] = []
    for f in fields:
        val = _resolve(event, f)
        if isinstance(val, float):
            val = round(val, round_digits)
        parts.append(val)
    return tuple(parts)


def detect_duplicates(
    events: list[CanonicalEvent],
    *,
    fields: list[str] | tuple[str, ...] | None = None,
    value_round_digits: int = DEFAULT_VALUE_ROUND_DIGITS,
) -> None:
    """Tag every event after the first with the same (subject, category, ts, value)."""
    field_tuple = tuple(fields) if fields is not None else DEFAULT_FIELDS
    seen: set[tuple] = set()
    for event in events:
        fp = _fingerprint(event, field_tuple, value_round_digits)
        if fp in seen:
            event.quality.flags.append(
                QualityFlag(
                    code="DUPLICATE_EVENT",
                    severity=Severity.WARNING,
                    stage="qualified",
                    message="Duplicate of an earlier event with the same fingerprint",
                )
            )
        else:
            seen.add(fp)

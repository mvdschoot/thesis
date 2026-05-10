from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from domain.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseValidator


def _parse_iso(ts: str) -> datetime | None:
    try:
        s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _resolve_window_bound(spec: str | None) -> datetime | None:
    if not spec:
        return None
    if spec.startswith("now"):
        delta = timedelta()
        rest = spec[3:]
        if rest.startswith("+") or rest.startswith("-"):
            sign = 1 if rest[0] == "+" else -1
            tail = rest[1:]
            if tail.endswith("d"):
                delta = timedelta(days=sign * int(tail[:-1]))
            elif tail.endswith("h"):
                delta = timedelta(hours=sign * int(tail[:-1]))
        return datetime.now(timezone.utc) + delta
    return _parse_iso(spec)


class TimestampValidator(BaseValidator):
    """Parseable ISO 8601 + within configured window."""

    @property
    def name(self) -> str:
        return "timestamp"

    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        ts = event.timestamp
        if not ts:
            return flags
        parsed = _parse_iso(ts)
        if parsed is None:
            flags.append(
                QualityFlag(
                    code="TIMESTAMP_UNPARSEABLE",
                    severity=Severity.ERROR,
                    stage="validated",
                    message=f"Could not parse timestamp '{ts}' as ISO 8601",
                )
            )
            return flags

        window = (overrides or {}).get("timestamp_window") or rules.get(
            "timestamp_window"
        )
        if window:
            min_dt = _resolve_window_bound(window.get("min"))
            max_dt = _resolve_window_bound(window.get("max"))
            if min_dt and parsed.tzinfo is None:
                parsed_cmp = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed_cmp = parsed
            if min_dt and min_dt.tzinfo is None:
                min_dt = min_dt.replace(tzinfo=timezone.utc)
            if max_dt and max_dt.tzinfo is None:
                max_dt = max_dt.replace(tzinfo=timezone.utc)

            if (min_dt and parsed_cmp < min_dt) or (max_dt and parsed_cmp > max_dt):
                flags.append(
                    QualityFlag(
                        code="TIMESTAMP_OUT_OF_WINDOW",
                        severity=Severity.WARNING,
                        stage="validated",
                        message=f"Timestamp '{ts}' outside allowed window",
                    )
                )
        return flags

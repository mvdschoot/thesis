from __future__ import annotations

import re
from datetime import datetime, timezone

from domain.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseHeuristic

ISO_8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TimestampNormalizer(BaseHeuristic):
    """Detects and normalizes various timestamp formats to ISO 8601 with Z suffix.

    `accept_formats` extends the built-in ISO/date-only handling with
    user-supplied strptime patterns (e.g. "%m/%d/%Y %I:%M:%S %p"). The
    sentinels "iso" and "date" can also appear in the list — they map back
    to the built-in regex paths and are present so configs can express
    "only accept ISO" by listing them explicitly.
    """

    def __init__(self, accept_formats: list[str] | None = None) -> None:
        self._accept_formats: list[str] = list(accept_formats) if accept_formats else []

    @property
    def name(self) -> str:
        return "timestamp-normalizer"

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        event.timestamp = self._normalize(event.timestamp, event, "timestamp")
        if event.timestamp_end is not None:
            event.timestamp_end = self._normalize(
                event.timestamp_end, event, "timestamp_end"
            )
        return event

    def _normalize(self, ts: str, event: CanonicalEvent, field: str) -> str:
        if not ts:
            return ts

        if ISO_8601.match(ts) and ts.endswith("Z"):
            return ts

        if ISO_8601.match(ts) and not ts.endswith("Z"):
            event.quality.flags.append(
                QualityFlag(
                    code="TIMEZONE_ASSUMED_UTC",
                    severity=Severity.INFO,
                    stage="cleaned",
                    message=f"{field}: appended Z to timestamp without timezone",
                )
            )
            return ts + "Z" if "+" not in ts and "-" not in ts[10:] else ts

        if DATE_ONLY.match(ts):
            event.quality.flags.append(
                QualityFlag(
                    code="DATE_ONLY_TIMESTAMP",
                    severity=Severity.INFO,
                    stage="cleaned",
                    message=f"{field}: expanded date-only to start of day",
                )
            )
            return ts + "T00:00:00.000Z"

        for fmt in self._accept_formats:
            if fmt in ("iso", "date"):
                continue
            try:
                parsed = datetime.strptime(ts, fmt)
            except (ValueError, TypeError):
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            millis = parsed.microsecond // 1000
            normalized = parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"
            event.quality.flags.append(
                QualityFlag(
                    code="TIMESTAMP_FORMAT_PARSED",
                    severity=Severity.INFO,
                    stage="cleaned",
                    message=f"{field}: parsed with format {fmt!r}",
                )
            )
            return normalized

        return ts

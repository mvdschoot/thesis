from __future__ import annotations

import re

from domain.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseHeuristic

ISO_8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TimestampNormalizer(BaseHeuristic):
    """Detects and normalizes various timestamp formats to ISO 8601 with Z suffix."""

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

        return ts

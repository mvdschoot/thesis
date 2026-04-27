from __future__ import annotations

from typing import Any

from ..models.canonical import CanonicalEvent, QualityFlag, Severity
from .base import BaseValidator


class RangeValidator(BaseValidator):
    """Check payload.value against the category's plausibility range."""

    @property
    def name(self) -> str:
        return "range"

    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        rng = (overrides or {}).get("range") or rules.get("range")
        if not rng:
            return []
        value = event.payload.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return []  # Non-numeric value: range check N/A.

        min_v = rng.get("min")
        max_v = rng.get("max")
        violation = (min_v is not None and value < min_v) or (
            max_v is not None and value > max_v
        )
        if not violation:
            return []

        on_violation = rng.get("on_violation") or {}
        severity_str = on_violation.get("severity", "warning")
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.WARNING
        code = on_violation.get("code", "RANGE_VIOLATION")
        return [
            QualityFlag(
                code=code,
                severity=severity,
                stage="validated",
                message=f"Value {value} outside [{min_v}, {max_v}] for category {event.category!r}",
            )
        ]

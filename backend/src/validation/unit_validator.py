from __future__ import annotations

from typing import Any

from ..models.canonical import CanonicalEvent, QualityFlag, Severity
from .base import BaseValidator


class UnitValidator(BaseValidator):
    """Check payload.unit against the category's whitelist (if any)."""

    @property
    def name(self) -> str:
        return "unit"

    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        whitelist = (overrides or {}).get("unit_whitelist") or rules.get(
            "unit_whitelist"
        )
        if not whitelist:
            return []  # No constraint declared for this category.

        unit = event.payload.unit
        if unit is None:
            return []  # Unit-inference happens upstream; absence not flagged here.
        if unit not in whitelist:
            return [
                QualityFlag(
                    code="UNIT_NOT_IN_WHITELIST",
                    severity=Severity.WARNING,
                    stage="validated",
                    message=f"Unit {unit!r} not in whitelist {whitelist} for category {event.category!r}",
                )
            ]
        return []

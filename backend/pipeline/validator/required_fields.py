from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseValidator


class RequiredFieldsValidator(BaseValidator):
    """Subject id, timestamp, type, category must be present and non-empty."""

    @property
    def name(self) -> str:
        return "required-fields"

    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        missing: list[str] = []
        if not event.subject_id:
            missing.append("subject_id")
        if not event.timestamp:
            missing.append("timestamp")
        if not event.category or event.category == "unknown":
            missing.append("category")
        if event.type is None:
            missing.append("type")
        if missing:
            flags.append(
                QualityFlag(
                    code="MISSING_REQUIRED_FIELD",
                    severity=Severity.ERROR,
                    stage="validated",
                    message=f"Missing or empty: {', '.join(missing)}",
                )
            )
        return flags

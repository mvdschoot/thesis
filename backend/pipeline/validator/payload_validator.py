from __future__ import annotations

from typing import Any

from shared.models import CanonicalEvent, EventType, QualityFlag, Severity

from .base import BaseValidator


class PayloadValidator(BaseValidator):
    """Per-EventType minimum payload requirements."""

    @property
    def name(self) -> str:
        return "payload"

    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        p = event.payload
        has_value = p.value is not None and p.value != ""
        has_components = bool(p.components)

        empty = False
        if event.type in (EventType.MEASUREMENT, EventType.OBSERVATION, EventType.SUMMARY):
            empty = not (has_value or has_components)
        elif event.type == EventType.SURVEY:
            empty = not (has_value or has_components or p.label)
        elif event.type == EventType.EVENT:
            empty = not (has_value or has_components or p.label)
        elif event.type == EventType.SESSION:
            empty = not (has_value or has_components or event.duration_seconds)

        if empty:
            flags.append(
                QualityFlag(
                    code="PAYLOAD_EMPTY",
                    severity=Severity.ERROR,
                    stage="validated",
                    message=f"Event type {event.type.value!r} requires a payload value, components, or label",
                )
            )
        return flags

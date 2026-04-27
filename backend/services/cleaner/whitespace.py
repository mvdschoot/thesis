from __future__ import annotations

from shared.models import CanonicalEvent

from .base import BaseHeuristic


class WhitespaceStripper(BaseHeuristic):
    """Trim leading/trailing whitespace on string fields. Silent."""

    @property
    def name(self) -> str:
        return "whitespace-stripper"

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        if isinstance(event.payload.label, str):
            event.payload.label = event.payload.label.strip()
        if isinstance(event.payload.value, str):
            event.payload.value = event.payload.value.strip()
        if isinstance(event.payload.raw_value, str):
            event.payload.raw_value = event.payload.raw_value.strip()
        return event

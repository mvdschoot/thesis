from __future__ import annotations

from domain.coerce import try_coerce_numeric
from domain.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseHeuristic


class TypeCoercer(BaseHeuristic):
    """Coerce numeric strings on payload.value and components to int/float."""

    @property
    def name(self) -> str:
        return "type-coercer"

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        coerced_any = False

        new_value, changed = try_coerce_numeric(event.payload.value)
        if changed:
            event.payload.value = new_value
            coerced_any = True

        if event.payload.components:
            for c in event.payload.components:
                new_c_value, c_changed = try_coerce_numeric(c.value)
                if c_changed:
                    c.value = new_c_value
                    coerced_any = True

        if coerced_any:
            event.quality.flags.append(
                QualityFlag(
                    code="VALUE_COERCED",
                    severity=Severity.INFO,
                    stage="cleaned",
                    message="Numeric string value(s) coerced to int/float",
                )
            )
        return event

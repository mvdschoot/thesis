from __future__ import annotations

from shared.models import CanonicalEvent, QualityFlag, Severity

from .base import BaseHeuristic


def _try_coerce(value: object) -> tuple[object, bool]:
    if not isinstance(value, str):
        return value, False
    s = value.strip()
    if not s:
        return value, False
    try:
        if "." in s or "e" in s or "E" in s:
            return float(s), True
        return int(s), True
    except ValueError:
        try:
            return float(s), True
        except ValueError:
            return value, False


class TypeCoercer(BaseHeuristic):
    """Coerce numeric strings on payload.value and components to int/float."""

    @property
    def name(self) -> str:
        return "type-coercer"

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        coerced_any = False

        new_value, changed = _try_coerce(event.payload.value)
        if changed:
            event.payload.value = new_value
            coerced_any = True

        if event.payload.components:
            for c in event.payload.components:
                new_c_value, c_changed = _try_coerce(c.value)
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

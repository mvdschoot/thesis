from __future__ import annotations

from ..models.canonical import CanonicalEvent, QualityFlag, Severity
from .base import BaseHeuristic

# Default unit mappings by (source, category)
DEFAULT_UNITS: dict[tuple[str, str], str] = {
    ("fitbit", "steps"): "count",
    ("fitbit", "distance"): "km",
    ("fitbit", "calories"): "kcal",
    ("fitbit", "floors"): "count",
    ("fitbit", "elevation"): "m",
    ("fitbit", "heart-rate"): "bpm",
    ("fitbit", "heart-rate-zone"): "min",
    ("withings", "weight"): "kg",
    ("withings", "fat-ratio"): "%",
    ("withings", "fat-mass"): "kg",
    ("withings", "muscle-mass"): "kg",
    ("withings", "bone-mass"): "kg",
}


class UnitInferrer(BaseHeuristic):
    """Infers units from source + category when the adapter hasn't set them.

    Can be extended with custom mappings at construction time.
    """

    def __init__(
        self, extra_mappings: dict[tuple[str, str], str] | None = None
    ) -> None:
        self._units = dict(DEFAULT_UNITS)
        if extra_mappings:
            self._units.update(extra_mappings)

    @property
    def name(self) -> str:
        return "unit-inferrer"

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        if event.payload.unit is not None:
            return event

        key = (event.context.source, event.category)
        inferred = self._units.get(key)
        if inferred:
            event.payload.unit = inferred
            event.quality.flags.append(
                QualityFlag(
                    code="UNIT_INFERRED",
                    severity=Severity.INFO,
                    stage="structured",
                    message=f"Unit '{inferred}' inferred from ({key[0]}, {key[1]})",
                )
            )

        return event

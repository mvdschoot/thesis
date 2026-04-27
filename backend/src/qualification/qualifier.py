from __future__ import annotations

from typing import Any

from ..models.canonical import CanonicalEvent, Severity, Stage
from .completeness import compute_completeness
from .duplicates import detect_duplicates
from .outliers import detect_outliers

_CONFORMANCE_FLAG_PREFIXES = (
    "RANGE_",
    "UNIT_",
    "TIMESTAMP_",
    "MISSING_",
    "PAYLOAD_",
)
_CONFORMANCE_FLAG_CODES = {
    "HR_OUT_OF_RANGE",
    "HR_ZONE_MINUTES_OUT_OF_RANGE",
    "STEPS_OUT_OF_RANGE",
    "DISTANCE_OUT_OF_RANGE",
    "CALORIES_OUT_OF_RANGE",
    "FLOORS_OUT_OF_RANGE",
    "ELEVATION_OUT_OF_RANGE",
    "WEIGHT_OUT_OF_RANGE",
    "HEIGHT_OUT_OF_RANGE",
    "BODY_FAT_OUT_OF_RANGE",
    "FAT_MASS_OUT_OF_RANGE",
    "FAT_FREE_MASS_OUT_OF_RANGE",
    "MUSCLE_MASS_OUT_OF_RANGE",
    "BONE_MASS_OUT_OF_RANGE",
    "BODY_WATER_OUT_OF_RANGE",
    "BP_SYS_OUT_OF_RANGE",
    "BP_DIA_OUT_OF_RANGE",
    "SPO2_OUT_OF_RANGE",
    "PWV_OUT_OF_RANGE",
    "SCORE_OUT_OF_RANGE",
}


def _is_conformance_flag(code: str) -> bool:
    if code in _CONFORMANCE_FLAG_CODES:
        return True
    return any(code.startswith(p) for p in _CONFORMANCE_FLAG_PREFIXES)


class Qualifier:
    """Cross-event judgement: completeness, duplicates, statistical outliers,
    and the final conformance + plausibility verdicts.
    """

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules: dict[str, Any] = rules or {}
        thresholds = self.rules.get("plausibility_thresholds") or {}
        self.warning_count_for_review: int = int(
            thresholds.get("warning_count_for_review", 1)
        )

    def _category_rules(self, category: str) -> dict[str, Any]:
        return (self.rules.get("categories") or {}).get(category) or {}

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        # 1. completeness — per-event
        for event in events:
            ratio, present, expected = compute_completeness(
                event, self._category_rules(event.category)
            )
            event.quality.completeness = ratio
            event.quality.present_field_count = present
            event.quality.expected_field_count = expected

        # 2. duplicates — cross-event
        detect_duplicates(events)

        # 3. outliers — per (subject, category) group
        detect_outliers(events)

        # 4. conformance + plausibility — derived from accumulated flags
        for event in events:
            self._assign_conformance(event)
            self._assign_plausibility(event)
            event.stage = Stage.QUALIFIED
            # Strip the internal override key now that it's no longer needed.
            if event.extensions and "_quality_override" in event.extensions:
                del event.extensions["_quality_override"]
                if not event.extensions:
                    event.extensions = None

        return events

    def _assign_conformance(self, event: CanonicalEvent) -> None:
        has_conformance_issue = any(
            _is_conformance_flag(f.code) and f.severity != Severity.INFO
            for f in event.quality.flags
        )
        event.quality.conformance = "issues" if has_conformance_issue else "ok"

    def _assign_plausibility(self, event: CanonicalEvent) -> None:
        warnings = sum(
            1 for f in event.quality.flags if f.severity == Severity.WARNING
        )
        if event.has_severity(Severity.ERROR):
            event.quality.plausibility = "exclude"
        elif warnings >= self.warning_count_for_review:
            event.quality.plausibility = "review"
        else:
            event.quality.plausibility = "ok"

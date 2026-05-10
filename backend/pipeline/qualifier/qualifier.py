from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent, Severity, Stage

from .completeness import compute_completeness
from .config import DEFAULT_CHECK_ORDER, QualifyConfig
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

    Per-config tunables (Hampel k, fingerprint fields, plausibility threshold)
    layer on top of the global `quality_rules.yaml`. Per-config completeness
    `expected_fields` likewise overlay the global category rules.
    """

    def __init__(
        self,
        rules: dict[str, Any] | None = None,
        config: QualifyConfig | None = None,
    ) -> None:
        self.rules: dict[str, Any] = rules or {}
        self.config: QualifyConfig = config or QualifyConfig()
        # Plausibility threshold: per-config block wins over the global default.
        global_thresholds = (self.rules.get("plausibility_thresholds") or {})
        if config is not None:
            self.warning_count_for_review = self.config.plausibility.warning_count_for_review
        else:
            self.warning_count_for_review = int(
                global_thresholds.get("warning_count_for_review", 1)
            )
        if self.config.enabled is None:
            self._enabled = set(DEFAULT_CHECK_ORDER)
        else:
            self._enabled = set(self.config.enabled)

    def _category_rules(self, category: str) -> dict[str, Any]:
        merged: dict[str, Any] = dict(
            (self.rules.get("categories") or {}).get(category) or {}
        )
        # Per-config completeness overlay for this category's expected_fields.
        override_fields = self.config.completeness.expected_fields.get(category)
        if override_fields is not None:
            merged["expected_fields"] = list(override_fields)
        return merged

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        if "completeness" in self._enabled:
            for event in events:
                ratio, present, expected = compute_completeness(
                    event, self._category_rules(event.category)
                )
                event.quality.completeness = ratio
                event.quality.present_field_count = present
                event.quality.expected_field_count = expected

        if "duplicates" in self._enabled:
            detect_duplicates(
                events,
                fields=self.config.duplicates.fields,
                value_round_digits=self.config.duplicates.value_round_digits,
            )

        if "outliers" in self._enabled:
            detect_outliers(
                events,
                hampel_k=self.config.outliers.hampel_k,
                min_group_size=self.config.outliers.min_group_size,
            )

        for event in events:
            if "conformance" in self._enabled:
                self._assign_conformance(event)
            if "plausibility" in self._enabled:
                self._assign_plausibility(event)
            event.stage = Stage.QUALIFIED

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

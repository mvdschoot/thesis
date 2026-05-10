from __future__ import annotations

from typing import Any

from shared.models import CanonicalEvent, QualityFlag, Stage

from .base import BaseValidator
from .payload_validator import PayloadValidator
from .range_validator import RangeValidator
from .required_fields import RequiredFieldsValidator
from .timestamp_validator import TimestampValidator
from .unit_validator import UnitValidator


def _flag_key(f: QualityFlag) -> tuple:
    return (f.code, f.stage, f.message)


class ValidationRunner:
    """Runs the per-event validator chain and tags events with QualityFlags.

    Quality rules are looked up by `event.category`. Per-event overrides may
    be supplied via `event.extensions["_quality_override"]` (placed there by
    the adapter when a YAML emit-rule declares `quality_overrides:`).
    """

    DEFAULT_VALIDATORS: list[BaseValidator]

    def __init__(
        self,
        rules: dict[str, Any] | None = None,
        validators: list[BaseValidator] | None = None,
    ) -> None:
        self.rules: dict[str, Any] = rules or {}
        self.validators: list[BaseValidator] = validators if validators is not None else [
            RequiredFieldsValidator(),
            TimestampValidator(),
            PayloadValidator(),
            UnitValidator(),
            RangeValidator(),
        ]

    def _category_rules(self, category: str) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if "timestamp_window" in self.rules:
            merged["timestamp_window"] = self.rules["timestamp_window"]
        cat_rules = (self.rules.get("categories") or {}).get(category) or {}
        merged.update(cat_rules)
        return merged

    @staticmethod
    def _pop_override(event: CanonicalEvent) -> dict[str, Any] | None:
        if not event.extensions:
            return None
        return event.extensions.get("_quality_override")

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        cat_rules = self._category_rules(event.category)
        overrides = self._pop_override(event)
        existing_keys = {_flag_key(f) for f in event.quality.flags}
        for v in self.validators:
            for flag in v.validate(event, cat_rules, overrides):
                key = _flag_key(flag)
                if key in existing_keys:
                    continue
                event.quality.flags.append(flag)
                existing_keys.add(key)
        event.stage = Stage.VALIDATED
        return event

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        return [self.apply(e) for e in events]

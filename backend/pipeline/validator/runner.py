from __future__ import annotations

import copy
from typing import Any

from domain.models import CanonicalEvent, QualityFlag, Stage

from .base import BaseValidator
from .config import DEFAULT_VALIDATOR_ORDER, ValidateConfig
from .payload_validator import PayloadValidator
from .range_validator import RangeValidator
from .required_fields import RequiredFieldsValidator
from .timestamp_validator import TimestampValidator
from .unit_validator import UnitValidator

# Map the user-facing closed-enum names to validator classes.
_VALIDATOR_FACTORY: dict[str, type[BaseValidator]] = {
    "required_fields": RequiredFieldsValidator,
    "timestamp_window": TimestampValidator,
    "payload_shape": PayloadValidator,
    "unit_whitelist": UnitValidator,
    "range": RangeValidator,
}


def _flag_key(f: QualityFlag) -> tuple:
    return (f.code, f.stage, f.message)


def _merge_rules(
    global_rules: dict[str, Any], config: ValidateConfig | None
) -> dict[str, Any]:
    """Layer per-config overrides on top of the global quality_rules.yaml.

    Shallow replace per-key inside `categories.<name>` — providing `range`
    replaces the global range wholesale, providing `unit_whitelist`
    replaces that list wholesale. Top-level `timestamp_window` likewise.
    """
    merged = copy.deepcopy(global_rules) or {}
    if config is None:
        return merged
    if config.timestamp_window is not None:
        merged["timestamp_window"] = dict(config.timestamp_window)
    if config.categories:
        cats = merged.setdefault("categories", {})
        for cat_name, overrides in config.categories.items():
            target = cats.setdefault(cat_name, {})
            target.update(overrides)
    return merged


def _select_validators(config: ValidateConfig | None) -> list[BaseValidator]:
    """Build the validator chain in canonical order, filtered by `enabled`.
    Honour the canonical order regardless of how the user listed names."""
    if config is None or config.enabled is None:
        names = DEFAULT_VALIDATOR_ORDER
    else:
        enabled_set = set(config.enabled)
        names = tuple(n for n in DEFAULT_VALIDATOR_ORDER if n in enabled_set)
    return [_VALIDATOR_FACTORY[n]() for n in names]


class ValidationRunner:
    """Runs the per-event validator chain and tags events with QualityFlags.

    Quality rules are looked up by `event.category`. Per-event overrides may
    be supplied via `event.extensions["_quality_override"]` (placed there by
    the adapter when a YAML emit-rule declares `quality_overrides:`).
    """

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

    @classmethod
    def from_config(
        cls,
        global_rules: dict[str, Any],
        config: ValidateConfig | None,
    ) -> "ValidationRunner":
        return cls(
            rules=_merge_rules(global_rules, config),
            validators=_select_validators(config),
        )

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

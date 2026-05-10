"""Parsed `validate:` block from the YAML pipeline config.

Empty / missing block → `None`, which the validator runtime interprets as
"run all five validators using the global quality_rules.yaml" (current behavior).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALIDATOR_NAMES: tuple[str, ...] = (
    "required_fields",
    "timestamp_window",
    "payload_shape",
    "unit_whitelist",
    "range",
)

DEFAULT_VALIDATOR_ORDER: tuple[str, ...] = VALIDATOR_NAMES


@dataclass
class ValidateConfig:
    enabled: list[str] | None = None
    timestamp_window: dict[str, Any] | None = None
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ValidateConfig | None":
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError(
                f"validate must be a mapping, got {type(raw).__name__}"
            )

        enabled = raw.get("enabled")
        if enabled is not None:
            if not isinstance(enabled, list):
                raise ValueError(
                    f"validate.enabled must be a list, got {type(enabled).__name__}"
                )
            unknown = [n for n in enabled if n not in VALIDATOR_NAMES]
            if unknown:
                raise ValueError(
                    f"validate.enabled contains unknown names {unknown}; "
                    f"expected subset of {list(VALIDATOR_NAMES)}"
                )

        ts_window = raw.get("timestamp_window")
        if ts_window is not None and not isinstance(ts_window, dict):
            raise ValueError(
                f"validate.timestamp_window must be a mapping, got {type(ts_window).__name__}"
            )

        categories = raw.get("categories") or {}
        if not isinstance(categories, dict):
            raise ValueError(
                f"validate.categories must be a mapping, got {type(categories).__name__}"
            )
        for cat_name, cat_rules in categories.items():
            if not isinstance(cat_rules, dict):
                raise ValueError(
                    f"validate.categories.{cat_name} must be a mapping, got {type(cat_rules).__name__}"
                )

        return cls(
            enabled=list(enabled) if enabled is not None else None,
            timestamp_window=dict(ts_window) if ts_window is not None else None,
            categories={k: dict(v) for k, v in categories.items()},
        )

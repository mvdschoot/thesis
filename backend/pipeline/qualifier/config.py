"""Parsed `qualify:` block from the YAML pipeline config.

Empty / missing block → `None`, which the qualifier runtime interprets as
"run all five checks using global quality_rules.yaml + hardcoded defaults"
(current behavior).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CHECK_NAMES: tuple[str, ...] = (
    "completeness",
    "duplicates",
    "outliers",
    "conformance",
    "plausibility",
)

DEFAULT_CHECK_ORDER: tuple[str, ...] = CHECK_NAMES


@dataclass
class OutliersConfig:
    hampel_k: float = 3.5
    min_group_size: int = 5

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "OutliersConfig":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError(
                f"qualify.outliers must be a mapping, got {type(raw).__name__}"
            )
        return cls(
            hampel_k=float(raw.get("hampel_k", 3.5)),
            min_group_size=int(raw.get("min_group_size", 5)),
        )


@dataclass
class DuplicatesConfig:
    fields: list[str] = field(
        default_factory=lambda: ["subject_id", "category", "timestamp", "payload.value"]
    )
    value_round_digits: int = 3

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "DuplicatesConfig":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError(
                f"qualify.duplicates must be a mapping, got {type(raw).__name__}"
            )
        fields_raw = raw.get("fields")
        if fields_raw is not None and not isinstance(fields_raw, list):
            raise ValueError(
                f"qualify.duplicates.fields must be a list, got {type(fields_raw).__name__}"
            )
        instance = cls()
        if fields_raw is not None:
            instance.fields = list(fields_raw)
        if "value_round_digits" in raw:
            instance.value_round_digits = int(raw["value_round_digits"])
        return instance


@dataclass
class PlausibilityConfig:
    warning_count_for_review: int = 1

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PlausibilityConfig":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError(
                f"qualify.plausibility must be a mapping, got {type(raw).__name__}"
            )
        return cls(
            warning_count_for_review=int(raw.get("warning_count_for_review", 1)),
        )


@dataclass
class CompletenessConfig:
    expected_fields: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CompletenessConfig":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError(
                f"qualify.completeness must be a mapping, got {type(raw).__name__}"
            )
        expected_fields = raw.get("expected_fields") or {}
        if not isinstance(expected_fields, dict):
            raise ValueError(
                f"qualify.completeness.expected_fields must be a mapping, "
                f"got {type(expected_fields).__name__}"
            )
        for cat, fields_list in expected_fields.items():
            if not isinstance(fields_list, list):
                raise ValueError(
                    f"qualify.completeness.expected_fields.{cat} must be a list, "
                    f"got {type(fields_list).__name__}"
                )
        return cls(
            expected_fields={k: list(v) for k, v in expected_fields.items()},
        )


@dataclass
class QualifyConfig:
    enabled: list[str] | None = None
    outliers: OutliersConfig = field(default_factory=OutliersConfig)
    duplicates: DuplicatesConfig = field(default_factory=DuplicatesConfig)
    plausibility: PlausibilityConfig = field(default_factory=PlausibilityConfig)
    completeness: CompletenessConfig = field(default_factory=CompletenessConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "QualifyConfig | None":
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError(
                f"qualify must be a mapping, got {type(raw).__name__}"
            )

        enabled = raw.get("enabled")
        if enabled is not None:
            if not isinstance(enabled, list):
                raise ValueError(
                    f"qualify.enabled must be a list, got {type(enabled).__name__}"
                )
            unknown = [n for n in enabled if n not in CHECK_NAMES]
            if unknown:
                raise ValueError(
                    f"qualify.enabled contains unknown names {unknown}; "
                    f"expected subset of {list(CHECK_NAMES)}"
                )

        return cls(
            enabled=list(enabled) if enabled is not None else None,
            outliers=OutliersConfig.from_dict(raw.get("outliers")),
            duplicates=DuplicatesConfig.from_dict(raw.get("duplicates")),
            plausibility=PlausibilityConfig.from_dict(raw.get("plausibility")),
            completeness=CompletenessConfig.from_dict(raw.get("completeness")),
        )

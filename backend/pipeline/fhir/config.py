"""Parsed `fhir:` block from the YAML pipeline config.

Empty / missing block → ``None``, which the FHIR runtime interprets as
"FHIR output disabled — return an empty bundle and leave events at their
existing stage." Present block → :class:`FhirConfig` instance with closed-enum
validation on ``bundle_type`` and ``include``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BUNDLE_TYPES: tuple[str, ...] = ("transaction", "collection")
RESOURCE_KINDS: tuple[str, ...] = ("Patient", "Observation", "Device", "Provenance", "Questionnaire")
DEFAULT_INCLUDE: tuple[str, ...] = ("Patient", "Observation", "Questionnaire")


@dataclass
class FhirConfig:
    enabled: bool = True
    bundle_type: str = "transaction"
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "FhirConfig | None":
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError(
                f"fhir must be a mapping, got {type(raw).__name__}"
            )

        enabled = bool(raw.get("enabled", True))

        bundle_type = raw.get("bundle_type", "transaction")
        if bundle_type not in BUNDLE_TYPES:
            raise ValueError(
                f"fhir.bundle_type={bundle_type!r} not in {list(BUNDLE_TYPES)}"
            )

        include_raw = raw.get("include")
        if include_raw is None:
            include = list(DEFAULT_INCLUDE)
        else:
            if not isinstance(include_raw, list):
                raise ValueError(
                    f"fhir.include must be a list, got {type(include_raw).__name__}"
                )
            unknown = [n for n in include_raw if n not in RESOURCE_KINDS]
            if unknown:
                raise ValueError(
                    f"fhir.include contains unknown kinds {unknown}; "
                    f"expected subset of {list(RESOURCE_KINDS)}"
                )
            include = list(include_raw)

        return cls(enabled=enabled, bundle_type=bundle_type, include=include)

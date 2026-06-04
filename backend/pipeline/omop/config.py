"""Parsed ``omop:`` block from the YAML pipeline config.

Empty / missing block → ``None``, which the OMOP runtime interprets as
"run with default settings" — OMOP CDM output is enabled by default (see
:func:`pipeline.omop.run`). Present block → :class:`OmopConfig` with closed-enum
validation on ``include``; an explicit ``enabled: false`` is the only way to
disable the stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# "concept" is accepted as a valid name (so a config may list it without a
# validation error), but the CONCEPT vocabulary table is always emitted
# alongside the clinical tables — it defines the custom (2B) concepts the
# clinical rows reference, so it is not gated like an optional clinical table.
TABLE_KINDS: tuple[str, ...] = (
    "person",
    "measurement",
    "observation",
    "device_exposure",
    "observation_period",
    "concept",
)
DEFAULT_INCLUDE: tuple[str, ...] = (
    "person",
    "measurement",
    "observation",
    "device_exposure",
    "observation_period",
)


@dataclass
class OmopConfig:
    enabled: bool = True
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "OmopConfig | None":
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError(
                f"omop must be a mapping, got {type(raw).__name__}"
            )

        enabled = bool(raw.get("enabled", True))

        include_raw = raw.get("include")
        if include_raw is None:
            include = list(DEFAULT_INCLUDE)
        else:
            if not isinstance(include_raw, list):
                raise ValueError(
                    f"omop.include must be a list, got {type(include_raw).__name__}"
                )
            unknown = [n for n in include_raw if n not in TABLE_KINDS]
            if unknown:
                raise ValueError(
                    f"omop.include contains unknown tables {unknown}; "
                    f"expected subset of {list(TABLE_KINDS)}"
                )
            include = list(include_raw)

        return cls(enabled=enabled, include=include)

"""Parsed `clean:` block from the YAML pipeline config.

Empty / missing block → `None`, which the cleaner runtime interprets as
"use the default chain with default parameters" (current behavior).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HEURISTIC_NAMES: tuple[str, ...] = (
    "whitespace",
    "timestamp_normalizer",
    "type_coercer",
    "unit_inferrer",
)

DEFAULT_HEURISTIC_ORDER: tuple[str, ...] = HEURISTIC_NAMES


@dataclass
class HeuristicSpec:
    """One entry of `clean.heuristics`.

    YAML forms:
        - "whitespace"                                       (string shorthand)
        - { name: timestamp_normalizer, accept_formats: [...] }
    """
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any, *, index: int) -> "HeuristicSpec":
        if isinstance(value, str):
            name, params = value, {}
        elif isinstance(value, dict):
            if "name" not in value:
                raise ValueError(
                    f"clean.heuristics[{index}] missing required key 'name'"
                )
            name = value["name"]
            params = {k: v for k, v in value.items() if k != "name"}
        else:
            raise ValueError(
                f"clean.heuristics[{index}] must be a string or mapping, got {type(value).__name__}"
            )
        if name not in HEURISTIC_NAMES:
            raise ValueError(
                f"clean.heuristics[{index}].name={name!r} not in {list(HEURISTIC_NAMES)}"
            )
        return cls(name=name, params=params)


@dataclass
class CleanConfig:
    heuristics: list[HeuristicSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CleanConfig | None":
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError(f"clean must be a mapping, got {type(raw).__name__}")
        heuristics_raw = raw.get("heuristics")
        if heuristics_raw is None:
            return cls(heuristics=[])
        if not isinstance(heuristics_raw, list):
            raise ValueError(
                f"clean.heuristics must be a list, got {type(heuristics_raw).__name__}"
            )
        heuristics = [
            HeuristicSpec.from_value(v, index=i) for i, v in enumerate(heuristics_raw)
        ]
        return cls(heuristics=heuristics)

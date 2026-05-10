from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent, Stage

from .base import BaseHeuristic, HeuristicChain
from .coercion import TypeCoercer
from .config import CleanConfig, HeuristicSpec
from .timestamp import TimestampNormalizer
from .units import UnitInferrer
from .whitespace import WhitespaceStripper


def _build_heuristic(spec: HeuristicSpec) -> BaseHeuristic:
    """Map a HeuristicSpec to a fresh heuristic instance.

    Unknown parameter keys for a given heuristic raise a clear ValueError
    so the YAML author sees their typo at config-parse time.
    """
    name = spec.name
    params: dict[str, Any] = spec.params
    if name == "whitespace":
        _reject_unknown_params(name, params, allowed=set())
        return WhitespaceStripper()
    if name == "timestamp_normalizer":
        _reject_unknown_params(name, params, allowed={"accept_formats"})
        return TimestampNormalizer(accept_formats=params.get("accept_formats"))
    if name == "type_coercer":
        _reject_unknown_params(name, params, allowed=set())
        return TypeCoercer()
    if name == "unit_inferrer":
        _reject_unknown_params(name, params, allowed={"mappings"})
        return UnitInferrer(mappings=params.get("mappings"))
    raise ValueError(f"Unknown cleaner heuristic name: {name!r}")


def _reject_unknown_params(name: str, params: dict[str, Any], *, allowed: set[str]) -> None:
    extra = set(params) - allowed
    if extra:
        raise ValueError(
            f"clean.heuristics[{name}] has unknown params {sorted(extra)}; "
            f"expected subset of {sorted(allowed) if allowed else 'no params'}"
        )


def build_chain(config: CleanConfig | None) -> HeuristicChain:
    """Build the heuristic chain for one pipeline run. `None` → default chain
    (whitespace → timestamp_normalizer → type_coercer → unit_inferrer)."""
    if config is None or not config.heuristics:
        return HeuristicChain([
            WhitespaceStripper(),
            TimestampNormalizer(),
            TypeCoercer(),
            UnitInferrer(),
        ])
    return HeuristicChain([_build_heuristic(s) for s in config.heuristics])


class Cleaner:
    """Per-event syntactic cleaning. Runs an ordered chain of heuristics that
    transform values (timestamps, units, whitespace, numeric coercion) and
    advances each event's stage to CLEANED.
    """

    def __init__(self, heuristics: list[BaseHeuristic] | None = None) -> None:
        chain = heuristics if heuristics is not None else [
            WhitespaceStripper(),
            TimestampNormalizer(),
            TypeCoercer(),
            UnitInferrer(),
        ]
        self._chain = HeuristicChain(chain)

    @classmethod
    def from_config(cls, config: CleanConfig | None) -> "Cleaner":
        return cls(heuristics=build_chain(config).heuristics)

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        event = self._chain.apply(event)
        event.stage = Stage.CLEANED
        return event

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        return [self.apply(e) for e in events]

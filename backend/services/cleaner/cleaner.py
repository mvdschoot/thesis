from __future__ import annotations

from shared.models import CanonicalEvent, Stage

from .base import BaseHeuristic, HeuristicChain
from .coercion import TypeCoercer
from .timestamp import TimestampNormalizer
from .units import UnitInferrer
from .whitespace import WhitespaceStripper


class Cleaner:
    """Per-event syntactic cleaning. Runs an ordered chain of heuristics that
    transform values (timestamps, units, whitespace, numeric coercion) and
    advances each event's stage to CLEANED.
    """

    DEFAULT_CHAIN: list[BaseHeuristic]

    def __init__(self, heuristics: list[BaseHeuristic] | None = None) -> None:
        chain = heuristics if heuristics is not None else [
            WhitespaceStripper(),
            TimestampNormalizer(),
            TypeCoercer(),
            UnitInferrer(),
        ]
        self._chain = HeuristicChain(chain)

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        event = self._chain.apply(event)
        event.stage = Stage.CLEANED
        return event

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        return [self.apply(e) for e in events]

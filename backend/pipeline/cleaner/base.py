from __future__ import annotations

from abc import ABC, abstractmethod

from shared.models import CanonicalEvent


class BaseHeuristic(ABC):
    """Abstract base class for heuristics that enrich or transform canonical events.

    Heuristics are applied after adapter transformation. They can modify, enrich,
    or flag events without changing the fundamental structure.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this heuristic."""
        ...

    @abstractmethod
    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        """Apply this heuristic to a single canonical event.

        Returns the (possibly modified) event. Implementations should
        add quality flags when they make changes.
        """
        ...


class HeuristicChain:
    """Applies a sequence of heuristics to canonical events in order."""

    def __init__(self, heuristics: list[BaseHeuristic] | None = None) -> None:
        self._heuristics: list[BaseHeuristic] = heuristics or []

    def add(self, heuristic: BaseHeuristic) -> None:
        self._heuristics.append(heuristic)

    def apply(self, event: CanonicalEvent) -> CanonicalEvent:
        for heuristic in self._heuristics:
            event = heuristic.apply(event)
        return event

    def apply_all(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        return [self.apply(e) for e in events]

    @property
    def heuristics(self) -> list[BaseHeuristic]:
        return list(self._heuristics)

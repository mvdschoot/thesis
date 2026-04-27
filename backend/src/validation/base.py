from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models.canonical import CanonicalEvent, QualityFlag


class BaseValidator(ABC):
    """Validators ASSERT properties of an event without mutating its values.

    They return a list of QualityFlags. The runner appends them to the event.
    Distinct from BaseHeuristic so the type system makes the no-mutation
    contract obvious.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def validate(
        self,
        event: CanonicalEvent,
        rules: dict[str, Any],
        overrides: dict[str, Any] | None,
    ) -> list[QualityFlag]:
        """Return any flags raised by this validator. May be empty."""
        ...

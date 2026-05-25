from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from domain.models import CanonicalEvent, SourceMetadata

if TYPE_CHECKING:
    from .diagnostics import DiagnosticsCollector


class BaseAdapter(ABC):
    """Abstract base class for source-to-canonical adapters.

    Each adapter knows how to transform records from a specific data source
    into canonical events. Implement `can_handle` to declare which records
    this adapter supports, and `transform` to do the conversion.
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Identifier for the source type this adapter handles (e.g., 'fitbit')."""
        ...

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter (e.g., 'fitbit-v1')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of this adapter (e.g., '1.0.0')."""
        ...

    @abstractmethod
    def can_handle(self, metadata: SourceMetadata, record: dict[str, Any]) -> bool:
        """Return True if this adapter can transform the given record."""
        ...

    @abstractmethod
    def transform(
        self,
        metadata: SourceMetadata,
        record: dict[str, Any],
        *,
        record_index: int = 0,
        collector: "DiagnosticsCollector | None" = None,
    ) -> list[CanonicalEvent]:
        """Transform a single source record into one or more canonical events.

        `record_index` is the 0-based position of this record in the input
        batch — exposed to YAML configs via ``@record_index``.
        `collector` is optional — subclasses may ignore it. When passed, it
        records per-rule and per-record skip reasons for diagnostics.
        """
        ...

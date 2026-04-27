from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shared.models import CanonicalEvent, SourceMetadata


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
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        """Transform a single source record into one or more canonical events."""
        ...

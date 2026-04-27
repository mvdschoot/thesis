from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator

from shared.models import SourceMetadata


class BaseConnector(ABC):
    """Abstract base class for data source connectors.

    A connector reads raw data from a source (file, API, stream) and yields
    individual records along with metadata describing the source.
    """

    @abstractmethod
    def read(self, path: Path) -> Iterator[tuple[SourceMetadata, dict[str, Any]]]:
        """Read data from the given path and yield (metadata, record) pairs.

        Each record is a single raw data object from the source, exactly as
        it appeared in the input (no transformation).
        """
        ...

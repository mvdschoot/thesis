from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class SourceMetadata:
    """Describes the data source a connector is reading from."""

    source_name: str          # e.g., "fitbit", "withings", "redcap"
    format: str               # e.g., "json", "csv", "xlsx"
    device: str | None = None # e.g., "Fitbit Charge 6"
    modality: str = "unknown" # e.g., "wearable", "survey", "sensor"
    description: str = ""     # free-text description of the data


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

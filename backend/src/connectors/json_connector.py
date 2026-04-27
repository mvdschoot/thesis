from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .base import BaseConnector, SourceMetadata


class JsonConnector(BaseConnector):
    """Reads JSON files and yields individual records.

    Handles both JSON arrays (yields each element) and single JSON objects
    (yields the object once).
    """

    def __init__(self, metadata: SourceMetadata) -> None:
        self.metadata = metadata

    def read(self, path: Path) -> Iterator[tuple[SourceMetadata, dict[str, Any]]]:
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for record in data:
                yield self.metadata, record
        elif isinstance(data, dict):
            yield self.metadata, data
        else:
            raise ValueError(
                f"Expected JSON array or object at {path}, got {type(data).__name__}"
            )

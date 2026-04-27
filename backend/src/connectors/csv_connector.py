from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator

from .base import BaseConnector, SourceMetadata


class CsvConnector(BaseConnector):
    """Reads CSV files (DictReader) and yields one dict per row.

    Values arrive as strings; the cleaning stage's TypeCoercer handles
    numeric coercion downstream. Encoding defaults to utf-8-sig so an
    Excel BOM is silently stripped.
    """

    def __init__(
        self,
        metadata: SourceMetadata,
        *,
        delimiter: str = ",",
        encoding: str = "utf-8-sig",
    ) -> None:
        self.metadata = metadata
        self.delimiter = delimiter
        self.encoding = encoding

    def read(self, path: Path) -> Iterator[tuple[SourceMetadata, dict[str, Any]]]:
        path = Path(path)
        with open(path, "r", encoding=self.encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            for row in reader:
                yield self.metadata, dict(row)

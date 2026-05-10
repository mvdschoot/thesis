"""Connector stage: raw input → list[record].

Dispatches by `format` to JsonConnector or CsvConnector. Returns the
SourceMetadata used downstream and the parsed record list.
"""
from __future__ import annotations

import json as _json
import logging
import tempfile
from pathlib import Path
from typing import Any

from domain.models import SourceMetadata

from .base import BaseConnector
from .csv_connector import CsvConnector
from .json_connector import JsonConnector

__all__ = ["BaseConnector", "CsvConnector", "JsonConnector", "run"]

logger = logging.getLogger("pipeline.connector")


def run(
    data: Any,
    *,
    format: str = "json",
    source: str | None = None,
    device: str | None = None,
) -> tuple[SourceMetadata, list[dict[str, Any]]]:
    metadata = SourceMetadata(source_name=source or "", format=format, device=device)

    if format == "csv":
        if not isinstance(data, str):
            raise ValueError("format='csv' requires data to be raw CSV text.")
        suffix = ".csv"
    else:
        suffix = ".json"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8", newline=""
    ) as tmp:
        if format == "csv":
            tmp.write(data)
        else:
            _json.dump(data, tmp)
        tmp_path = Path(tmp.name)

    try:
        connector = CsvConnector(metadata) if format == "csv" else JsonConnector(metadata)
        records: list[dict[str, Any]] = []
        for _meta, record in connector.read(tmp_path):
            records.append(record)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    logger.info("connector emitted %d records (format=%s)", len(records), format)
    return metadata, records

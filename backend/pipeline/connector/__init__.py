"""Connector stage: raw input → list[record].

Dispatches by `format` to JsonConnector or CsvConnector. Returns the
SourceMetadata used downstream and the parsed record list.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any

from domain.models import SourceMetadata

from .base import BaseConnector
from .csv_connector import CsvConnector
from .json_connector import JsonConnector

__all__ = ["BaseConnector", "CsvConnector", "JsonConnector", "run"]

logger = logging.getLogger("pipeline.connector")


def _parse_csv_in_memory(data: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(data))
    return [dict(row) for row in reader]


def _parse_json_in_memory(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"Expected JSON array or object, got {type(data).__name__}")


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
        records = _parse_csv_in_memory(data)
    else:
        records = _parse_json_in_memory(data)

    logger.info("connector emitted %d records (format=%s)", len(records), format)
    return metadata, records

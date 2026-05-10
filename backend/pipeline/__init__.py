"""Pipeline orchestrator.

Chains the five harmonization stages — connector, adapter, cleaner,
validator, qualifier — as plain in-process Python calls. Each stage is a
subpackage exposing a single `run(...)` function; this module wires them
together so the API layer can invoke the whole pipeline with one call.
"""
from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent

from . import adapter, cleaner, connector, qualifier, validator

__all__ = ["run_pipeline"]


def run_pipeline(
    *,
    data: Any,
    yaml_text: str,
    source: str | None = None,
    format: str = "json",
    device: str | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    """Run a record (or batch) through every stage and return (events, stats)."""
    metadata, records = connector.run(data, format=format, source=source, device=device)
    structured = adapter.run(records, metadata=metadata, yaml_text=yaml_text)
    cleaned = cleaner.run(structured)
    validated = validator.run(cleaned)
    qualified, stats = qualifier.run(validated)
    return qualified, stats

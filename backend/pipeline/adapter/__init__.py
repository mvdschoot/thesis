"""Adapter stage: list[record] → list[CanonicalEvent stage=STRUCTURED]."""
from __future__ import annotations

import logging
from typing import Any

import yaml

from domain.models import CanonicalEvent, SourceMetadata

from .base import BaseAdapter
from .config_adapter import ConfigAdapter
from .diagnostics import AdapterDiagnostics, DiagnosticsCollector
from .registry import AdapterRegistry

__all__ = [
    "BaseAdapter",
    "ConfigAdapter",
    "AdapterRegistry",
    "AdapterDiagnostics",
    "DiagnosticsCollector",
    "run",
]

logger = logging.getLogger("pipeline.adapter")


def run(
    records: list[dict[str, Any]],
    *,
    metadata: SourceMetadata,
    yaml_text: str | None = None,
    adapter: ConfigAdapter | None = None,
    diagnostics: DiagnosticsCollector | None = None,
) -> list[CanonicalEvent]:
    """Run the adapter against `records`. Accepts either pre-parsed
    `adapter` (preferred — caller can reuse it for clean/validate/qualify
    blocks) or raw `yaml_text` for standalone use.

    Pass `diagnostics` (a `DiagnosticsCollector`) to capture per-rule and
    per-record skip reasons. The collector is mutated in place; callers
    invoke `.finalize(len(events))` to retrieve the result. Optional —
    callers that don't pass one behave exactly as before.
    """
    if adapter is None:
        if yaml_text is None:
            raise ValueError("adapter.run requires either `adapter` or `yaml_text`")
        parsed = yaml.safe_load(yaml_text) or {}
        if not isinstance(parsed, dict):
            raise ValueError("YAML must be a mapping at the top level.")
        adapter = ConfigAdapter.from_dict(parsed)
    registry = AdapterRegistry()
    registry.register(adapter)

    events: list[CanonicalEvent] = []
    for idx, record in enumerate(records):
        if diagnostics is not None:
            diagnostics.start_record(idx)
        chosen = registry.get_adapter(metadata, record)
        if chosen is None:
            if diagnostics is not None:
                diagnostics.record_unmatched(
                    registry.explain_no_match(metadata, record, idx)
                )
            continue
        if diagnostics is not None:
            diagnostics.record_matched()
        for ev in chosen.transform(metadata, record, record_index=idx, collector=diagnostics):
            events.append(ev)

    logger.info("adapter produced %d events", len(events))
    return events

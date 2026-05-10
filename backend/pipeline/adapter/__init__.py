"""Adapter stage: list[record] → list[CanonicalEvent stage=STRUCTURED]."""
from __future__ import annotations

import logging
from typing import Any

import yaml

from domain.models import CanonicalEvent, SourceMetadata

from .base import BaseAdapter
from .config_adapter import ConfigAdapter
from .registry import AdapterRegistry

__all__ = ["BaseAdapter", "ConfigAdapter", "AdapterRegistry", "run"]

logger = logging.getLogger("pipeline.adapter")


def run(
    records: list[dict[str, Any]],
    *,
    metadata: SourceMetadata,
    yaml_text: str,
) -> list[CanonicalEvent]:
    parsed = yaml.safe_load(yaml_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML must be a mapping at the top level.")
    adapter = ConfigAdapter.from_dict(parsed)
    registry = AdapterRegistry()
    registry.register(adapter)

    events: list[CanonicalEvent] = []
    for record in records:
        chosen = registry.get_adapter(metadata, record)
        if chosen is None:
            continue
        for ev in chosen.transform(metadata, record):
            events.append(ev)

    logger.info("adapter produced %d events", len(events))
    return events

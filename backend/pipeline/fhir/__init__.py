"""FHIR stage: events stage=QUALIFIED → stage=STANDARDIZED.

Builds a FHIR R4 Bundle from the qualified canonical events and stamps
``Stage.STANDARDIZED`` on every event when enabled. Returns the events
plus a stats dict whose ``"fhir"`` key carries the bundle, resource count,
and serialized size — the orchestrator hoists this onto the top-level
:class:`api.models.TransformResponse.bundle` field for the frontend.

When ``config`` is ``None`` or ``config.enabled is False``, this is a
no-op: events pass through untouched and ``stats["fhir"]`` is ``None``.
"""
from __future__ import annotations

import logging
from typing import Any

from domain.models import CanonicalEvent, Stage

from .builder import build_bundle
from .config import FhirConfig

__all__ = ["FhirConfig", "build_bundle", "run"]

logger = logging.getLogger("pipeline.fhir")


def run(
    events: list[CanonicalEvent],
    *,
    config: FhirConfig | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    if config is None or not config.enabled:
        return events, {"fhir": None}

    bundle = build_bundle(events, config=config)
    for event in events:
        event.stage = Stage.STANDARDIZED

    dangling: list[str] = bundle.pop("__dangling_refs", [])
    if dangling:
        logger.warning(
            "fhir bundle has %d dangling reference(s): %s",
            len(dangling), dangling[:5],
        )
    entry_count = len(bundle.get("entry", []))
    size_bytes = entry_count * 600
    stats = {
        "fhir": {
            "bundle": bundle,
            "resource_count": entry_count,
            "size_bytes": size_bytes,
            "dangling_refs": dangling,
        }
    }
    logger.info(
        "fhir built bundle: type=%s resources=%d size_bytes≈%d",
        bundle.get("type"),
        entry_count,
        size_bytes,
    )
    return events, stats

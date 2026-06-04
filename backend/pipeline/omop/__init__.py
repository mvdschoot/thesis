"""OMOP CDM stage: mapped events → OMOP CDM v5.4 table rows.

Runs as a parallel projection alongside the FHIR builder — both read
the same MAPPED canonical events and produce their output in the stats
dict.  The orchestrator hoists ``stats["omop"]`` onto the top-level
:pyattr:`api.models.TransformResponse.omop_cdm` field.

When ``config`` is ``None`` (the ``omop:`` block was omitted) the stage runs
with default settings — OMOP CDM output is *enabled* by default. Only an explicit
``omop.enabled: false`` makes this a no-op (events pass through untouched and
``stats["omop"]`` is ``None``).
"""
from __future__ import annotations

import logging
from typing import Any

from domain.models import CanonicalEvent

from .builder import build_cdm
from .config import OmopConfig

__all__ = ["OmopConfig", "build_cdm", "run"]

logger = logging.getLogger("pipeline.omop")


def run(
    events: list[CanonicalEvent],
    *,
    config: OmopConfig | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    # An omitted `omop:` block (config is None) means "run with defaults" —
    # OMOP output is on by default. Only an explicit enabled: false disables it.
    if config is None:
        config = OmopConfig()
    if not config.enabled:
        return events, {"omop": None}

    cdm = build_cdm(events, config=config)

    table_stats = {
        "person_count": len(cdm["person"]),
        "measurement_count": len(cdm["measurement"]),
        "observation_count": len(cdm["observation"]),
        "device_exposure_count": len(cdm["device_exposure"]),
        "observation_period_count": len(cdm["observation_period"]),
        "concept_count": len(cdm.get("concept", [])),
        "unmapped_count": len(cdm.get("unmapped", [])),
        "component_rows": cdm.pop("_component_rows", 0),
    }
    cdm["stats"] = table_stats

    logger.info(
        "omop built cdm: measurement=%d observation=%d custom_concepts=%d unmapped=%d",
        table_stats["measurement_count"],
        table_stats["observation_count"],
        table_stats["concept_count"],
        table_stats["unmapped_count"],
    )
    return events, {"omop": cdm}

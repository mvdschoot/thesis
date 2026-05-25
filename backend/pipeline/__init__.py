"""Pipeline orchestrator.

Chains the five harmonization stages — connector, adapter, cleaner,
validator, qualifier — as plain in-process Python calls. Each stage is a
subpackage exposing a single `run(...)` function; this module wires them
together so the API layer can invoke the whole pipeline with one call.

The YAML config is parsed once here so the cleaner / validator / qualifier
blocks can be forwarded as kwargs to the matching stages.
"""
from __future__ import annotations

from typing import Any

import yaml

from domain.models import CanonicalEvent

from . import adapter, cleaner, connector, fhir, mapper, omop, qualifier, validator
from .adapter.config_adapter import ConfigAdapter
from .adapter.diagnostics import AdapterDiagnostics, DiagnosticsCollector

__all__ = ["run_pipeline", "AdapterDiagnostics"]


def _strip_quality_overrides(events: list[CanonicalEvent]) -> None:
    """Remove the `_quality_override` extension key the adapter writes for
    per-rule overrides. Runs after the qualifier today; lifted up here so
    cleanup still happens when the qualifier is disabled via `qualify.enabled`.
    """
    for event in events:
        if event.extensions and "_quality_override" in event.extensions:
            del event.extensions["_quality_override"]
            if not event.extensions:
                event.extensions = None


def run_pipeline(
    *,
    data: Any,
    yaml_text: str,
    source: str | None = None,
    format: str = "json",
    device: str | None = None,
    concept_mappings: dict[str, dict[str, str]] | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any], AdapterDiagnostics]:
    """Run a record (or batch) through every stage and return
    `(events, stats, adapter_diagnostics)`. The diagnostics object captures
    why the adapter stage emitted (or didn't emit) events per rule — the
    other stages currently don't drop events, so this is adapter-scoped.
    """
    parsed = yaml.safe_load(yaml_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML must be a mapping at the top level.")
    config_adapter = ConfigAdapter.from_dict(parsed)

    collector = DiagnosticsCollector()

    metadata, records = connector.run(data, format=format, source=source, device=device)
    structured = adapter.run(
        records, metadata=metadata, adapter=config_adapter, diagnostics=collector,
    )
    adapter_diagnostics = collector.finalize(len(structured))
    cleaned = cleaner.run(structured, config=config_adapter.clean_block)
    validated = validator.run(cleaned, config=config_adapter.validate_block)
    qualified, stats = qualifier.run(validated, config=config_adapter.qualify_block)
    _strip_quality_overrides(qualified)
    mapped, mapper_stats = mapper.run(qualified, mappings=concept_mappings)
    stats.update(mapper_stats)
    standardized, fhir_stats = fhir.run(mapped, config=config_adapter.fhir_block)
    stats.update(fhir_stats)
    _, omop_stats = omop.run(standardized, config=config_adapter.omop_block)
    stats.update(omop_stats)
    return standardized, stats, adapter_diagnostics

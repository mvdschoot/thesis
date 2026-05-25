"""OMOP CDM builder: canonical events → CDM v5.4 table rows.

1. Collects unique FHIR codings from mapped events
2. Batch-resolves them via OMOPHub FHIR Resolver
3. Uses ``target_table`` from the API for domain-driven table routing
4. Populates both ``*_concept_id`` (standard) and ``*_source_concept_id``
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from domain.models import CanonicalEvent, EventType, Modality

from .config import OmopConfig
from .resolver import _EMPTY_RESOLUTION, batch_resolve
from .tables import (
    OmopDeviceExposure,
    OmopMeasurement,
    OmopObservation,
    OmopObservationPeriod,
    OmopPerson,
)

logger = logging.getLogger("pipeline.omop.builder")

_RESOLVABLE_SYSTEMS: frozenset[str] = frozenset({
    "http://loinc.org",
    "http://snomed.info/sct",
    "http://unitsofmeasure.org",
    "http://www.nlm.nih.gov/research/umls/rxnorm",
    "http://hl7.org/fhir/sid/icd-10-cm",
    "http://hl7.org/fhir/sid/icd-10",
    "http://hl7.org/fhir/sid/icd-9-cm",
    "http://www.ama-assn.org/go/cpt",
    "http://www.whocc.no/atc",
})

_TYPE_CONCEPT_FALLBACK: dict[str, int] = {
    "wearable": 32865,  # Patient self-report
    "scale": 705183,    # Patient self-tested
    "sensor": 32865,    # Patient self-report
    "app": 32865,       # Patient self-report
    "survey": 32862,    # Patient filled survey
    "game": 32865,      # Patient self-report
    "vr": 32865,        # Patient self-report
    "unknown": 32817,   # EHR
}

_MODALITY_SEARCH_QUERIES: dict[str, str] = {
    "wearable": "Patient self-report",
    "scale": "Patient self-tested",
    "sensor": "Patient self-report",
    "app": "Patient self-report",
    "survey": "Patient filled survey",
    "game": "Patient self-report",
    "vr": "Patient self-report",
    "unknown": "EHR",
}


def _resolve_type_concepts(modalities: set[str]) -> dict[str, int]:
    """Resolve type concept IDs from OMOPHub via bulk semantic search.

    Falls back to an empty dict on any failure — callers merge with
    ``_TYPE_CONCEPT_FALLBACK``.
    """
    try:
        from api.terminology import get_client as get_terminology_client
    except ImportError:
        return {}

    queries = [m for m in modalities if m in _MODALITY_SEARCH_QUERIES]
    if not queries:
        return {}

    seen_queries: dict[str, str] = {}
    searches: list[dict[str, str]] = []
    for mod in queries:
        q = _MODALITY_SEARCH_QUERIES[mod]
        if q not in seen_queries:
            seen_queries[q] = mod
            searches.append({"search_id": mod, "query": q})
        else:
            seen_queries[q + f"_{mod}"] = mod
            searches.append({"search_id": mod, "query": q})

    try:
        client = get_terminology_client()
        results = client.bulk_search(
            searches,
            defaults={
                "concept_class_id": "Type Concept",
                "standard_concept": "S",
                "threshold": 0.8,
                "page_size": 1,
            },
        )
    except Exception as exc:
        logger.warning("omop type concept resolution failed, using fallback: %s", exc)
        return {}

    resolved: dict[str, int] = {}
    for mod in queries:
        hits = results.get(mod, [])
        if hits and isinstance(hits[0], dict) and hits[0].get("concept_id"):
            resolved[mod] = int(hits[0]["concept_id"])
            logger.info(
                "omop type concept %s → %d (%s)",
                mod, resolved[mod], hits[0].get("display"),
            )
    return resolved


def _person_id(subject_id: str) -> int:
    digest = hashlib.sha256(subject_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (2**31)


def _extract_date(iso_ts: str) -> str:
    return iso_ts[:10] if iso_ts else ""


def _type_concept_id(modality: Modality, cache: dict[str, int]) -> int:
    return cache.get(modality.value, _TYPE_CONCEPT_FALLBACK.get(modality.value, 32817))


def _concept_codings(event: CanonicalEvent) -> dict[str, Any]:
    if not event.extensions:
        return {}
    bag = event.extensions.get("_concept_codings")
    return bag if isinstance(bag, dict) else {}


def _collect_unique_codings(events: list[CanonicalEvent]) -> list[dict[str, str]]:
    """Walk events and collect all unique (system, code) FHIR codings."""
    seen: set[tuple[str, str]] = set()
    codings: list[dict[str, str]] = []

    for event in events:
        if event.mapping and event.mapping.standard_system and event.mapping.standard_code:
            key = (event.mapping.standard_system, event.mapping.standard_code)
            if key not in seen:
                seen.add(key)
                codings.append({"system": key[0], "code": key[1]})

        cc = _concept_codings(event)
        for slot_key in ("unit", "component"):
            val = cc.get(slot_key)
            if not val:
                continue
            items = val if isinstance(val, list) else [val]
            for item in items:
                if not isinstance(item, dict):
                    continue
                sys = item.get("system", "")
                code = item.get("code", "")
                if sys and code and (sys, code) not in seen:
                    seen.add((sys, code))
                    codings.append({"system": sys, "code": code})

    return codings


def _resolve_coding(
    cache: dict[tuple[str, str], dict[str, Any]],
    system: str | None,
    code: str | None,
) -> dict[str, Any]:
    if not system or not code:
        return dict(_EMPTY_RESOLUTION)
    return cache.get((system, code), dict(_EMPTY_RESOLUTION))


def _fallback_table(event: CanonicalEvent) -> str:
    """Heuristic table routing when the resolver returns no target_table."""
    if event.type == EventType.SURVEY:
        return "observation"
    if event.type in (EventType.MEASUREMENT, EventType.SUMMARY):
        if isinstance(event.payload.value, (int, float)):
            return "measurement"
        return "observation"
    if event.type == EventType.OBSERVATION:
        if isinstance(event.payload.value, (int, float)):
            return "measurement"
        return "observation"
    return "observation"


def build_cdm(
    events: list[CanonicalEvent],
    *,
    config: OmopConfig,
) -> dict[str, Any]:
    unique_modalities = {ev.context.modality.value for ev in events}
    resolved_types = _resolve_type_concepts(unique_modalities)
    type_cache = {**_TYPE_CONCEPT_FALLBACK, **resolved_types}

    all_codings = _collect_unique_codings(events)
    unique_codings = [c for c in all_codings if c["system"] in _RESOLVABLE_SYSTEMS]
    skipped = len(all_codings) - len(unique_codings)
    if skipped:
        logger.info("omop skipped %d codings from non-resolvable systems", skipped)
    logger.info(
        "omop resolving %d unique codings: %s",
        len(unique_codings),
        [(c["system"], c["code"]) for c in unique_codings],
    )
    cache = batch_resolve(unique_codings) if unique_codings else {}
    for k, v in cache.items():
        logger.info(
            "omop resolved %s → concept_id=%s, mapping_type=%s, target_table=%s",
            k, v.get("standard_concept", {}).get("concept_id"), v.get("mapping_type"), v.get("target_table"),
        )

    resolution_summary: dict[str, int] = {"direct": 0, "mapped": 0, "semantic_match": 0, "unmapped": 0}
    for res in cache.values():
        mt = res.get("mapping_type", "unmapped")
        resolution_summary[mt] = resolution_summary.get(mt, 0) + 1

    persons: dict[int, OmopPerson] = {}
    measurements: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    devices: dict[str, OmopDeviceExposure] = {}
    periods: dict[int, dict[str, str]] = {}
    unmapped: list[dict[str, Any]] = []

    row_id = 0
    component_rows = 0
    device_id = 0

    include = set(config.include)

    for event in events:
        if event.quality and event.quality.plausibility == "exclude":
            continue
        if not event.payload:
            continue

        pid = _person_id(event.subject_id)
        if pid not in persons and "person" in include:
            persons[pid] = OmopPerson(
                person_id=pid,
                person_source_value=event.subject_id,
            )

        ts_date = _extract_date(event.timestamp)

        code_resolution = _resolve_coding(
            cache,
            event.mapping.standard_system if event.mapping else None,
            event.mapping.standard_code if event.mapping else None,
        )
        standard_concept_id = code_resolution.get("standard_concept", {}).get("concept_id", 0) or 0
        source_concept_id = code_resolution.get("source_concept", {}).get("concept_id", 0) or 0
        target_table = code_resolution.get("target_table", "") or _fallback_table(event)
        mapping_type = code_resolution.get("mapping_type", "unmapped")

        cc = _concept_codings(event)
        unit_coding = cc.get("unit")
        unit_resolution = _resolve_coding(
            cache,
            unit_coding.get("system") if isinstance(unit_coding, dict) else None,
            unit_coding.get("code") if isinstance(unit_coding, dict) else None,
        )
        unit_concept_id = unit_resolution.get("standard_concept", {}).get("concept_id", 0) or 0

        type_cid = _type_concept_id(event.context.modality, type_cache)

        # Route to CDM table. Events with concept_id=0 are still emitted
        # (OMOP convention: 0 = "No matching concept") — tag, don't drop.
        emitted = False

        if target_table == "measurement" and "measurement" in include:
            row_id += 1
            emitted = True
            m = OmopMeasurement(
                measurement_id=row_id,
                person_id=pid,
                measurement_concept_id=standard_concept_id,
                measurement_date=ts_date,
                measurement_datetime=event.timestamp,
                measurement_type_concept_id=type_cid,
                value_as_number=event.payload.value if isinstance(event.payload.value, (int, float)) else None,
                unit_concept_id=unit_concept_id,
                unit_source_value=event.payload.unit,
                measurement_source_value=event.category,
                measurement_source_concept_id=source_concept_id,
            )
            measurements.append(m.to_dict())

            if event.payload.components:
                comp_codings_list = cc.get("component", [])
                if not isinstance(comp_codings_list, list):
                    comp_codings_list = [comp_codings_list] if comp_codings_list else []

                for idx, comp in enumerate(event.payload.components):
                    comp_coding = comp_codings_list[idx] if idx < len(comp_codings_list) else None
                    comp_res = _resolve_coding(
                        cache,
                        comp_coding.get("system") if isinstance(comp_coding, dict) else None,
                        comp_coding.get("code") if isinstance(comp_coding, dict) else None,
                    )
                    comp_standard_id = comp_res.get("standard_concept", {}).get("concept_id", 0) or 0
                    comp_source_id = comp_res.get("source_concept", {}).get("concept_id", 0) or 0

                    comp_unit_id = 0
                    if comp.unit:
                        comp_unit_res = _resolve_coding(cache, "http://unitsofmeasure.org", comp.unit)
                        comp_unit_id = comp_unit_res.get("standard_concept", {}).get("concept_id", 0) or 0

                    row_id += 1
                    component_rows += 1
                    cm = OmopMeasurement(
                        measurement_id=row_id,
                        person_id=pid,
                        measurement_concept_id=comp_standard_id,
                        measurement_date=ts_date,
                        measurement_datetime=event.timestamp,
                        measurement_type_concept_id=type_cid,
                        value_as_number=comp.value if isinstance(comp.value, (int, float)) else None,
                        unit_concept_id=comp_unit_id,
                        unit_source_value=comp.unit,
                        measurement_source_value=f"{event.category}.{comp.name}",
                        measurement_source_concept_id=comp_source_id,
                    )
                    measurements.append(cm.to_dict())

        elif "observation" in include:
            row_id += 1
            emitted = True
            val_num = event.payload.value if isinstance(event.payload.value, (int, float)) else None
            val_str = str(event.payload.value) if not isinstance(event.payload.value, (int, float)) and event.payload.value is not None else None
            o = OmopObservation(
                observation_id=row_id,
                person_id=pid,
                observation_concept_id=standard_concept_id,
                observation_date=ts_date,
                observation_datetime=event.timestamp,
                observation_type_concept_id=type_cid,
                value_as_number=val_num,
                value_as_string=val_str,
                unit_concept_id=unit_concept_id,
                unit_source_value=event.payload.unit,
                observation_source_value=event.category,
                observation_source_concept_id=source_concept_id,
            )
            observations.append(o.to_dict())

        # Track unmapped codings for the audit trail (informational only —
        # the event is still in the clinical table with concept_id=0).
        if standard_concept_id == 0 and mapping_type == "unmapped" and emitted:
            unmapped.append({
                "event_id": event.event_id,
                "category": event.category,
                "coding": {
                    "system": event.mapping.standard_system if event.mapping else None,
                    "code": event.mapping.standard_code if event.mapping else None,
                },
                "mapping_type": mapping_type,
                "reason": "No standard concept found — emitted with concept_id=0",
            })

        if emitted:
            if pid not in periods:
                periods[pid] = {"start": ts_date, "end": ts_date}
            else:
                if ts_date < periods[pid]["start"]:
                    periods[pid]["start"] = ts_date
                if ts_date > periods[pid]["end"]:
                    periods[pid]["end"] = ts_date

        device_key = f"{event.context.source}|{event.context.device or ''}"
        if device_key not in devices and "device_exposure" in include and event.context.device:
            device_id += 1
            devices[device_key] = OmopDeviceExposure(
                device_exposure_id=device_id,
                person_id=pid,
                device_exposure_start_date=ts_date,
                device_exposure_end_date=ts_date,
                device_type_concept_id=type_cid,
                device_source_value=device_key,
            )
        elif device_key in devices:
            dev = devices[device_key]
            if ts_date and ts_date < dev.device_exposure_start_date:
                dev.device_exposure_start_date = ts_date
            if ts_date and ts_date > dev.device_exposure_end_date:
                dev.device_exposure_end_date = ts_date

    obs_periods: list[dict[str, Any]] = []
    if "observation_period" in include:
        for idx, (pid_key, span) in enumerate(periods.items(), start=1):
            obs_periods.append(
                OmopObservationPeriod(
                    observation_period_id=idx,
                    person_id=pid_key,
                    observation_period_start_date=span["start"],
                    observation_period_end_date=span["end"],
                ).to_dict()
            )

    return {
        "person": [p.to_dict() for p in persons.values()],
        "measurement": measurements,
        "observation": observations,
        "device_exposure": [d.to_dict() for d in devices.values()],
        "observation_period": obs_periods,
        "unmapped": unmapped,
        "resolution_stats": {
            "total_codings": len(unique_codings),
            "resolved": sum(v for k, v in resolution_summary.items() if k != "unmapped"),
            "failed": resolution_summary.get("unmapped", 0),
            "mapping_types": resolution_summary,
        },
        "_component_rows": component_rows,
    }

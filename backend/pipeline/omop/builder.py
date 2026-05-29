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
    OmopConcept,
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


_type_concept_cache: dict[str, int] = {}


def _resolve_type_concepts(modalities: set[str]) -> dict[str, int]:
    """Resolve type concept IDs from OMOPHub via bulk semantic search.

    Falls back to an empty dict on any failure — callers merge with
    ``_TYPE_CONCEPT_FALLBACK``.  Results are cached in-process so
    repeated batch-transform calls skip the network round-trip.
    """
    uncached = [m for m in modalities if m in _MODALITY_SEARCH_QUERIES and m not in _type_concept_cache]
    cached = {m: _type_concept_cache[m] for m in modalities if m in _type_concept_cache}

    if not uncached:
        return cached

    try:
        from api.terminology import get_client as get_terminology_client
    except ImportError:
        return cached

    seen_queries: dict[str, str] = {}
    searches: list[dict[str, str]] = []
    for mod in uncached:
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
        return cached

    for mod in uncached:
        hits = results.get(mod, [])
        if hits and isinstance(hits[0], dict) and hits[0].get("concept_id"):
            concept_id = int(hits[0]["concept_id"])
            _type_concept_cache[mod] = concept_id
            cached[mod] = concept_id
            logger.info(
                "omop type concept %s → %d (%s)",
                mod, concept_id, hits[0].get("display"),
            )
    return cached


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
        # unit is a single coding dict; component is a name->coding dict.
        candidates: list[Any] = []
        unit_val = cc.get("unit")
        if isinstance(unit_val, dict):
            candidates.append(unit_val)
        comp_val = cc.get("component")
        if isinstance(comp_val, dict):
            candidates.extend(comp_val.values())
        elif isinstance(comp_val, list):
            candidates.extend(comp_val)
        for item in candidates:
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


_CUSTOM_BASE = 2_000_000_000
_CUSTOM_SPAN = 100_000_000


def _custom_concept_id(system: str, code: str) -> int:
    """Deterministic OMOP custom concept_id (> 2,000,000,000) for a source code.

    Per OHDSI custom-concept guidance, source codes that don't map to a standard
    OMOP concept get an id in the 2-billion range.  Hash-based so the same
    (system, code) yields the same id across stateless requests; stays under the
    4-byte INTEGER ceiling (~2.147B).
    """
    digest = hashlib.sha256(f"{system}|{code}".encode("utf-8")).digest()
    return _CUSTOM_BASE + (int.from_bytes(digest[:4], "big") % _CUSTOM_SPAN) + 1


def _custom_vocab(source: str | None) -> str:
    """Source-specific vocabulary_id for custom concepts (OHDSI: add custom
    concepts to a new vocabulary specifically for your source)."""
    s = (source or "").strip()
    return f"Custom:{s}" if s else "Custom"


def _pick_concepts(
    res: dict[str, Any],
    *,
    system: str | None,
    code: str | None,
    picked_concept_id: int | None,
    picked_standard: str | None,
    display: str | None,
    domain_id: str,
    source: str | None,
    custom_by_key: dict[tuple[str, str], int],
    custom_rows: dict[int, OmopConcept],
    emit_concept: bool,
) -> tuple[int, int, str]:
    """Resolve one bound code into (standard_concept_id, source_concept_id, type).

    Precedence (see plan): the user-picked concept_id wins over re-resolution.
    Custom concepts (> 2B) live only in source_concept_id; concept_id stays 0
    when there is no standard mapping (OHDSI custom-concept rule).
    """
    res_standard = res.get("standard_concept", {}).get("concept_id", 0) or 0
    res_source = res.get("source_concept", {}).get("concept_id", 0) or 0
    res_type = res.get("mapping_type", "unmapped")

    picked = int(picked_concept_id) if picked_concept_id else 0
    is_std = picked_standard == "S"

    standard_id = res_standard or (picked if is_std else 0)
    source_id = picked or res_source

    if standard_id:
        mtype = res_type if res_type in ("direct", "mapped", "semantic_match") else "direct"
        return standard_id, source_id, mtype
    if source_id:
        # Real OMOP source concept but no standard target → concept_id stays 0.
        return 0, source_id, "source_only"

    # No OMOP concept at all → mint a custom (2-billion) concept, if a code exists.
    if system and code:
        key = (system, code)
        cid = custom_by_key.get(key)
        if cid is None:
            cid = _custom_concept_id(system, code)
            custom_by_key[key] = cid
            if emit_concept:
                custom_rows.setdefault(cid, OmopConcept(
                    concept_id=cid,
                    concept_name=(display or code),
                    domain_id=domain_id,
                    vocabulary_id=_custom_vocab(source),
                    concept_code=code,
                ))
        return 0, cid, "custom"

    return 0, 0, "unmapped"


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

    persons: dict[int, OmopPerson] = {}
    measurements: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    devices: dict[str, OmopDeviceExposure] = {}
    periods: dict[int, dict[str, str]] = {}
    unmapped: list[dict[str, Any]] = []

    # Custom ("2-billionaire") concepts minted for codes with no OMOP mapping.
    custom_by_key: dict[tuple[str, str], int] = {}
    custom_rows: dict[int, OmopConcept] = {}
    # Final per-code outcome (standard/source_only/custom/unmapped) for the
    # response summary — keyed by the unique clinical (system, code) bound.
    coding_outcomes: dict[tuple[str, str], str] = {}

    row_id = 0
    component_rows = 0
    device_id = 0

    include = set(config.include)
    # The CONCEPT vocabulary table is always recorded — custom concepts must be
    # defined wherever their 2B ids appear in *_source_concept_id.
    include_concept = True

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

        code_system = event.mapping.standard_system if event.mapping else None
        code_code = event.mapping.standard_code if event.mapping else None
        code_resolution = _resolve_coding(cache, code_system, code_code)
        target_table = code_resolution.get("target_table", "") or _fallback_table(event)
        domain_id = "Measurement" if target_table == "measurement" else "Observation"
        standard_concept_id, source_concept_id, mapping_type = _pick_concepts(
            code_resolution,
            system=code_system,
            code=code_code,
            picked_concept_id=event.mapping.concept_id if event.mapping else None,
            picked_standard=event.mapping.standard_concept if event.mapping else None,
            display=event.mapping.standard_display if event.mapping else None,
            domain_id=domain_id,
            source=event.context.source,
            custom_by_key=custom_by_key,
            custom_rows=custom_rows,
            emit_concept=include_concept,
        )
        if code_system and code_code:
            coding_outcomes[(code_system, code_code)] = mapping_type
        code_source_value = code_code or event.category

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
                measurement_source_value=code_source_value,
                measurement_source_concept_id=source_concept_id,
            )
            measurements.append(m.to_dict())

            if event.payload.components:
                comp_map = cc.get("component", {})
                if not isinstance(comp_map, dict):
                    comp_map = {}

                for comp in event.payload.components:
                    comp_coding = comp_map.get(comp.name)
                    is_coding = isinstance(comp_coding, dict)
                    comp_sys = comp_coding.get("system") if is_coding else None
                    comp_code = comp_coding.get("code") if is_coding else None
                    comp_res = _resolve_coding(cache, comp_sys, comp_code)
                    comp_standard_id, comp_source_id, comp_type = _pick_concepts(
                        comp_res,
                        system=comp_sys,
                        code=comp_code,
                        picked_concept_id=comp_coding.get("concept_id") if is_coding else None,
                        picked_standard=comp_coding.get("standard_concept") if is_coding else None,
                        display=comp_coding.get("display") if is_coding else comp.name,
                        domain_id="Measurement",
                        source=event.context.source,
                        custom_by_key=custom_by_key,
                        custom_rows=custom_rows,
                        emit_concept=include_concept,
                    )
                    if comp_sys and comp_code:
                        coding_outcomes[(comp_sys, comp_code)] = comp_type

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
                        measurement_source_value=comp_code or f"{event.category}.{comp.name}",
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
                observation_source_value=code_source_value,
                observation_source_concept_id=source_concept_id,
            )
            observations.append(o.to_dict())

        # Track truly-unmapped events for the audit trail (no standard AND no
        # source/custom concept — informational only; the row is still emitted
        # with concept_id=0). Rows with a custom 2B source concept are not here.
        if emitted and standard_concept_id == 0 and source_concept_id == 0:
            unmapped.append({
                "event_id": event.event_id,
                "category": event.category,
                "coding": {
                    "system": code_system,
                    "code": code_code,
                },
                "mapping_type": mapping_type,
                "reason": "No concept found — emitted with concept_id=0",
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

    # Per-code outcome summary, derived from the actual binding decisions
    # (standard / source_only / custom / unmapped) over unique clinical codes.
    resolution_summary: dict[str, int] = {
        "direct": 0, "mapped": 0, "semantic_match": 0,
        "source_only": 0, "custom": 0, "unmapped": 0,
    }
    for mt in coding_outcomes.values():
        resolution_summary[mt] = resolution_summary.get(mt, 0) + 1
    total_codings = len(coding_outcomes)

    return {
        "person": [p.to_dict() for p in persons.values()],
        "measurement": measurements,
        "observation": observations,
        "device_exposure": [d.to_dict() for d in devices.values()],
        "observation_period": obs_periods,
        "concept": [c.to_dict() for c in custom_rows.values()],
        "unmapped": unmapped,
        "resolution_stats": {
            "total_codings": total_codings,
            "resolved": total_codings - resolution_summary["unmapped"],
            "failed": resolution_summary["unmapped"],
            "mapping_types": resolution_summary,
        },
        "_component_rows": component_rows,
    }

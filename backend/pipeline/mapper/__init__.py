"""MAPPED stage — user-driven terminology binding.

Implements `Stage.MAPPED` by applying user-supplied `concept_mappings` to
qualified events. Mappings are keyed by slot (see :mod:`pipeline.mapper.keys`)
so one pick covers every event in the slot — the natural granularity for
wearable data.

For `code` slots the binding lands on `event.mapping` (the public Mapping
dataclass). Unit, component, and category bindings piggy-back on
`event.extensions["_concept_codings"]` — leading underscore so
`CanonicalEvent.to_dict()` strips it — to keep the public canonical model
unchanged. The FHIR builder reads from both places when emitting coding[].

Also detects the slots present in the current event set, so the API can
return them to the UI for the user to fill.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from domain.models import CanonicalEvent, MappingMethod, Stage

from pipeline.fhir.builder import _category_text_for_event
from .keys import (
    OBSERVATION_CATEGORY_CODES,
    category_key,
    code_key,
    component_key,
    component_unit_key,
    unit_key,
)

__all__ = ["run", "detect_slots", "ConceptSlot"]

logger = logging.getLogger("pipeline.mapper")


@dataclass
class ConceptSlot:
    """A slot of events that share the same coding target."""
    key: str
    kind: str  # "code" | "unit" | "component" | "category"
    label: str
    count: int
    sample: dict[str, Any]
    suggested_system: str | None
    default_coding: dict[str, str] | None
    current_mapping: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "count": self.count,
            "sample": self.sample,
            "suggested_system": self.suggested_system,
            "default_coding": self.default_coding,
            "current_mapping": self.current_mapping,
        }


LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"


def _event_sample(event: CanonicalEvent) -> dict[str, Any]:
    return {
        "value": event.payload.value if event.payload.value is not None else event.payload.raw_value,
        "unit": event.payload.unit,
        "timestamp": event.timestamp,
        "subject_id": event.subject_id,
    }


def detect_slots(
    events: list[CanonicalEvent],
    mappings: dict[str, dict[str, str]] | None,
) -> list[ConceptSlot]:
    """Walk events once and emit a deduplicated slot list.

    The order of the result is stable for the UI: code → unit → component →
    category, with insertion order within each kind.
    """
    mappings = mappings or {}
    code_slots: dict[str, ConceptSlot] = {}
    unit_slots: dict[str, ConceptSlot] = {}
    component_slots: dict[str, ConceptSlot] = {}
    category_slots: dict[str, ConceptSlot] = {}

    for event in events:
        # code slot — one per (category, label).
        k = code_key(event)
        if k in code_slots:
            code_slots[k].count += 1
        else:
            code_slots[k] = ConceptSlot(
                key=k,
                kind="code",
                label=(event.payload.label or event.category or "").strip() or "unknown",
                count=1,
                sample=_event_sample(event),
                suggested_system=LOINC_SYSTEM,
                default_coding=None,
                current_mapping=mappings.get(k),
            )

        # unit slot — only for events that actually carry a numeric unit.
        uk = unit_key(event)
        if uk is not None:
            if uk in unit_slots:
                unit_slots[uk].count += 1
            else:
                unit_slots[uk] = ConceptSlot(
                    key=uk,
                    kind="unit",
                    label=(event.payload.unit or "").strip(),
                    count=1,
                    sample=_event_sample(event),
                    suggested_system=UCUM_SYSTEM,
                    default_coding=None,
                    current_mapping=mappings.get(uk),
                )

        # component slots + their per-component units.
        for c in event.payload.components or []:
            ck = component_key(event, c)
            if ck in component_slots:
                component_slots[ck].count += 1
            else:
                component_slots[ck] = ConceptSlot(
                    key=ck,
                    kind="component",
                    label=f"{event.category} · {c.name}",
                    count=1,
                    sample={"value": c.value, "unit": c.unit, "timestamp": event.timestamp},
                    suggested_system=LOINC_SYSTEM,
                    default_coding=None,
                    current_mapping=mappings.get(ck),
                )
            cuk = component_unit_key(c.unit)
            if cuk is not None and cuk not in unit_slots:
                unit_slots[cuk] = ConceptSlot(
                    key=cuk,
                    kind="unit",
                    label=(c.unit or "").strip(),
                    count=1,
                    sample={"value": c.value, "unit": c.unit, "timestamp": event.timestamp},
                    suggested_system=UCUM_SYSTEM,
                    default_coding=None,
                    current_mapping=mappings.get(cuk),
                )

        # category slot — one per category text bucket.
        cat_text = _category_text_for_event(event)
        catk = category_key(cat_text)
        if catk in category_slots:
            category_slots[catk].count += 1
        else:
            default = OBSERVATION_CATEGORY_CODES.get(cat_text)
            category_slots[catk] = ConceptSlot(
                key=catk,
                kind="category",
                label=cat_text,
                count=1,
                sample=_event_sample(event),
                suggested_system="http://terminology.hl7.org/CodeSystem/observation-category",
                default_coding=default,
                current_mapping=mappings.get(catk),
            )

    return [
        *code_slots.values(),
        *unit_slots.values(),
        *component_slots.values(),
        *category_slots.values(),
    ]


def _apply_to_event(
    event: CanonicalEvent,
    mappings: dict[str, dict[str, str]],
) -> bool:
    """Apply mappings to a single event. Returns True if anything bound."""
    bound = False

    # Headline code → CanonicalEvent.mapping.
    code_m = mappings.get(code_key(event))
    if code_m:
        event.mapping.standard_code = code_m.get("code")
        event.mapping.standard_system = code_m.get("system")
        event.mapping.standard_display = code_m.get("display")
        event.mapping.method = MappingMethod.MANUAL.value
        bound = True

    # Unit/component/category go into the private extension bag.
    coded: dict[str, Any] = {}

    unit_k = unit_key(event)
    if unit_k:
        unit_m = mappings.get(unit_k)
        if unit_m:
            coded["unit"] = unit_m
            bound = True

    components_map: dict[str, dict[str, str]] = {}
    component_unit_map: dict[str, dict[str, str]] = {}
    for c in event.payload.components or []:
        cm = mappings.get(component_key(event, c))
        if cm:
            components_map[c.name] = cm
            bound = True
        cuk = component_unit_key(c.unit)
        if cuk:
            cum = mappings.get(cuk)
            if cum:
                component_unit_map[c.name] = cum
                bound = True
    if components_map:
        coded["component"] = components_map
    if component_unit_map:
        coded["component_unit"] = component_unit_map

    cat_text = _category_text_for_event(event)
    cat_m = mappings.get(category_key(cat_text))
    if cat_m:
        coded["category"] = cat_m
        bound = True
    elif cat_text in OBSERVATION_CATEGORY_CODES:
        # Auto-bind the four well-known buckets even if the user didn't pick —
        # category is short and standard, so emit a default coding[] regardless.
        coded["category"] = OBSERVATION_CATEGORY_CODES[cat_text]

    if coded:
        if event.extensions is None:
            event.extensions = {}
        event.extensions["_concept_codings"] = coded

    return bound


def run(
    events: list[CanonicalEvent],
    *,
    mappings: dict[str, dict[str, str]] | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    """Apply user concept mappings and stamp Stage.MAPPED on every event.

    The stage runs even when `mappings` is empty — we still want to emit
    default `category` codings and advance the stage marker so downstream
    code sees a uniform `MAPPED` state.
    """
    mappings = mappings or {}
    bound_count = 0
    for event in events:
        if _apply_to_event(event, mappings):
            bound_count += 1
        event.stage = Stage.MAPPED

    slots = detect_slots(events, mappings)
    unbound = sum(1 for s in slots if s.kind in ("code", "unit", "component") and not s.current_mapping)

    stats = {
        "mapper": {
            "slot_count": len(slots),
            "unbound_count": unbound,
            "events_bound": bound_count,
            "slots": [s.to_dict() for s in slots],
        }
    }
    logger.info(
        "mapper: slots=%d unbound=%d events_bound=%d/%d",
        len(slots), unbound, bound_count, len(events),
    )
    return events, stats

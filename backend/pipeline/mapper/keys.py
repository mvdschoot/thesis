"""Slot keys for user-driven concept binding.

A *slot* groups events that should share the same FHIR `coding[]`. The user
picks once per slot — wearable data is highly repetitive, so a single heart-rate
LOINC code typically covers thousands of events.

Keys are computed identically by the slot-detection pass and the mapper stage,
so both sides agree on grouping. Keep this module string-only — no I/O, no
imports beyond `domain`.
"""
from __future__ import annotations

from domain.models import CanonicalEvent, Component

# Category-text → standard observation-category code from
# http://terminology.hl7.org/CodeSystem/observation-category. Mirrors the
# four buckets emitted by `pipeline.fhir.builder._category_text_for_event`.
OBSERVATION_CATEGORY_CODES: dict[str, dict[str, str]] = {
    "vital-signs": {
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "vital-signs",
        "display": "Vital Signs",
    },
    "activity": {
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "activity",
        "display": "Activity",
    },
    "exam": {
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "exam",
        "display": "Exam",
    },
    "survey": {
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "survey",
        "display": "Survey",
    },
}


def _norm(s: str | None) -> str:
    return (s or "").strip()


def code_key(event: CanonicalEvent) -> str:
    """Slot key for `Observation.code` — the headline measurement coding."""
    label = _norm(event.payload.label) or _norm(event.category)
    return f"code|{_norm(event.category)}|{label}"


def unit_key(event: CanonicalEvent) -> str | None:
    """Slot key for `Observation.valueQuantity.code/system`.

    Returns None when there's no unit to bind (string-valued, boolean, or
    component-only events).
    """
    unit = _norm(event.payload.unit)
    if not unit:
        return None
    return f"unit|{unit}"


def component_unit_key(unit: str | None) -> str | None:
    """Per-component unit slot — same scheme as `unit_key` but accepts a raw unit."""
    u = _norm(unit)
    if not u:
        return None
    return f"unit|{u}"


def component_key(event: CanonicalEvent, component: Component) -> str:
    """Slot key for `Observation.component[].code`."""
    return f"component|{_norm(event.category)}|{_norm(component.name)}"


def category_key(category_text: str) -> str:
    """Slot key for `Observation.category[0].coding` — keyed by the bucket text."""
    return f"category|{_norm(category_text)}"

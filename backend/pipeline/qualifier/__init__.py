"""Qualifier stage: events stage=VALIDATED → stage=QUALIFIED.

Cross-event quality. Returns (events, stats) — the stats dict is what the
API surfaces alongside the events.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from domain.models import CanonicalEvent
from domain.rules import load_rules

from .qualifier import Qualifier

__all__ = ["Qualifier", "run"]

logger = logging.getLogger("pipeline.qualifier")

_RULES = load_rules()
_QUALIFIER = Qualifier(rules=_RULES)


def run(events: list[CanonicalEvent]) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    qualified = _QUALIFIER.apply_all(events)
    event_dicts = [e.to_dict() for e in qualified]
    logger.info("qualifier processed %d events", len(qualified))
    return qualified, _stats(event_dicts)


def _stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    flag_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    stage_counter: Counter[str] = Counter()
    plausibility_counter: Counter[str] = Counter()
    conformance_counter: Counter[str] = Counter()
    subjects: set[str] = set()
    for ev in events:
        subjects.add(ev.get("subject_id", ""))
        stage_counter[ev.get("stage", "unknown")] += 1
        quality = ev.get("quality") or {}
        if quality.get("plausibility"):
            plausibility_counter[quality["plausibility"]] += 1
        if quality.get("conformance"):
            conformance_counter[quality["conformance"]] += 1
        for f in quality.get("flags", []) or []:
            code = f.get("code")
            if code:
                flag_counter[code] += 1
            severity = f.get("severity")
            if severity:
                severity_counter[severity] += 1
    return {
        "count": len(events),
        "subjects": sorted(s for s in subjects if s),
        "flags": dict(flag_counter),
        "severity": dict(severity_counter),
        "stages": dict(stage_counter),
        "plausibility": dict(plausibility_counter),
        "conformance": dict(conformance_counter),
    }

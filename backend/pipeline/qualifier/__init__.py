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

from .config import QualifyConfig
from .qualifier import Qualifier

__all__ = ["Qualifier", "QualifyConfig", "run"]

logger = logging.getLogger("pipeline.qualifier")


def run(
    events: list[CanonicalEvent],
    *,
    config: QualifyConfig | None = None,
) -> tuple[list[CanonicalEvent], dict[str, Any]]:
    qualifier = Qualifier(rules=load_rules(), config=config)
    qualified = qualifier.apply_all(events)
    logger.info("qualifier processed %d events", len(qualified))
    return qualified, _stats(qualified)


def _stats(events: list[CanonicalEvent]) -> dict[str, Any]:
    flag_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    stage_counter: Counter[str] = Counter()
    plausibility_counter: Counter[str] = Counter()
    conformance_counter: Counter[str] = Counter()
    subjects: set[str] = set()
    for ev in events:
        subjects.add(ev.subject_id)
        stage_counter[ev.stage.value if ev.stage else "unknown"] += 1
        q = ev.quality
        if q.plausibility:
            plausibility_counter[q.plausibility] += 1
        if q.conformance:
            conformance_counter[q.conformance] += 1
        for f in q.flags:
            if f.code:
                flag_counter[f.code] += 1
            if f.severity:
                severity_counter[f.severity.value if hasattr(f.severity, "value") else f.severity] += 1
    return {
        "count": len(events),
        "subjects": sorted(s for s in subjects if s),
        "flags": dict(flag_counter),
        "severity": dict(severity_counter),
        "stages": dict(stage_counter),
        "plausibility": dict(plausibility_counter),
        "conformance": dict(conformance_counter),
    }

"""Qualifier worker: events stage=VALIDATED → stage=QUALIFIED.

Cross-event stage. Also computes the stats block the API returns and
publishes the final envelope to `transform-results`.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from shared.envelopes import (
    GROUP_QUALIFIER,
    TOPIC_RESULTS,
    TOPIC_VALIDATOR_OUT,
)
from shared.kafka_io import run_worker
from shared.models import CanonicalEvent
from shared.rules import load_rules

from .qualifier import Qualifier

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("qualifier-svc")

_RULES = load_rules()
_QUALIFIER = Qualifier(rules=_RULES)


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


async def process(env: dict[str, Any]) -> dict[str, Any]:
    request_id = env["request_id"]
    events = [CanonicalEvent.from_dict(d) for d in env.get("events", [])]
    qualified = _QUALIFIER.apply_all(events)
    event_dicts = [e.to_dict() for e in qualified]
    logger.info("[%s] qualifier processed %d events", request_id, len(qualified))
    return {
        "request_id": request_id,
        "metadata": env.get("metadata", {}),
        "events": event_dicts,
        "stats": _stats(event_dicts),
    }


async def main() -> None:
    await run_worker(
        name="qualifier",
        in_topic=TOPIC_VALIDATOR_OUT,
        out_topic=TOPIC_RESULTS,
        group_id=GROUP_QUALIFIER,
        process=process,
        error_topic=TOPIC_RESULTS,
    )


if __name__ == "__main__":
    asyncio.run(main())

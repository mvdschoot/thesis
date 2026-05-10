"""Validator worker: events stage=CLEANED → stage=VALIDATED."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.envelopes import (
    GROUP_VALIDATOR,
    TOPIC_CLEANER_OUT,
    TOPIC_RESULTS,
    TOPIC_VALIDATOR_OUT,
)
from shared.kafka_io import run_worker
from shared.models import CanonicalEvent
from shared.rules import load_rules

from .runner import ValidationRunner

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("validator-svc")

_RULES = load_rules()
_RUNNER = ValidationRunner(rules=_RULES)


async def process(env: dict[str, Any]) -> dict[str, Any]:
    request_id = env["request_id"]
    events = [CanonicalEvent.from_dict(d) for d in env.get("events", [])]
    validated = _RUNNER.apply_all(events)
    logger.info("[%s] validator processed %d events", request_id, len(validated))
    return {
        "request_id": request_id,
        "yaml": env["yaml"],
        "metadata": env["metadata"],
        "events": [e.to_dict() for e in validated],
    }


async def main() -> None:
    await run_worker(
        name="validator",
        in_topic=TOPIC_CLEANER_OUT,
        out_topic=TOPIC_VALIDATOR_OUT,
        group_id=GROUP_VALIDATOR,
        process=process,
        error_topic=TOPIC_RESULTS,
    )


if __name__ == "__main__":
    asyncio.run(main())

"""Cleaner worker: events stage=STRUCTURED → stage=CLEANED."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.envelopes import (
    GROUP_CLEANER,
    TOPIC_ADAPTER_OUT,
    TOPIC_CLEANER_OUT,
    TOPIC_RESULTS,
)
from shared.kafka_io import run_worker
from shared.models import CanonicalEvent

from .cleaner import Cleaner

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cleaner-svc")

_CLEANER = Cleaner()


async def process(env: dict[str, Any]) -> dict[str, Any]:
    request_id = env["request_id"]
    events = [CanonicalEvent.from_dict(d) for d in env.get("events", [])]
    cleaned = _CLEANER.apply_all(events)
    logger.info("[%s] cleaner processed %d events", request_id, len(cleaned))
    return {
        "request_id": request_id,
        "yaml": env["yaml"],
        "metadata": env["metadata"],
        "events": [e.to_dict() for e in cleaned],
    }


async def main() -> None:
    await run_worker(
        name="cleaner",
        in_topic=TOPIC_ADAPTER_OUT,
        out_topic=TOPIC_CLEANER_OUT,
        group_id=GROUP_CLEANER,
        process=process,
        error_topic=TOPIC_RESULTS,
    )


if __name__ == "__main__":
    asyncio.run(main())

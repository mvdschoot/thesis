"""Adapter worker: list[record] → list[CanonicalEvent stage=STRUCTURED]."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import yaml

from shared.envelopes import (
    GROUP_ADAPTER,
    TOPIC_ADAPTER_OUT,
    TOPIC_CONNECTOR_OUT,
    TOPIC_RESULTS,
)
from shared.kafka_io import run_worker
from shared.models import SourceMetadata

from .config_adapter import ConfigAdapter
from .registry import AdapterRegistry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("adapter-svc")


async def process(env: dict[str, Any]) -> dict[str, Any]:
    request_id = env["request_id"]
    parsed = yaml.safe_load(env["yaml"]) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML must be a mapping at the top level.")
    adapter = ConfigAdapter.from_dict(parsed)
    registry = AdapterRegistry()
    registry.register(adapter)

    meta_d = env["metadata"]
    metadata = SourceMetadata(
        source_name=meta_d["source_name"],
        format=meta_d["format"],
        device=meta_d.get("device"),
    )

    events: list[dict[str, Any]] = []
    for record in env.get("records", []):
        chosen = registry.get_adapter(metadata, record)
        if chosen is None:
            continue
        for ev in chosen.transform(metadata, record):
            events.append(ev.to_dict())

    logger.info("[%s] adapter produced %d events", request_id, len(events))
    return {
        "request_id": request_id,
        "yaml": env["yaml"],
        "metadata": meta_d,
        "events": events,
    }


async def main() -> None:
    await run_worker(
        name="adapter",
        in_topic=TOPIC_CONNECTOR_OUT,
        out_topic=TOPIC_ADAPTER_OUT,
        group_id=GROUP_ADAPTER,
        process=process,
        error_topic=TOPIC_RESULTS,
    )


if __name__ == "__main__":
    asyncio.run(main())

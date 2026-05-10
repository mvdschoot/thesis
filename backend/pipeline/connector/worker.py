"""Connector worker: raw input → list[record].

Consumes `transform-requests`, runs JsonConnector or CsvConnector based on
`format`, and produces a list of records to `connector-out`.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import tempfile
from pathlib import Path
from typing import Any

from shared.envelopes import (
    GROUP_CONNECTOR,
    TOPIC_CONNECTOR_OUT,
    TOPIC_REQUESTS,
    TOPIC_RESULTS,
)
from shared.kafka_io import run_worker
from shared.models import SourceMetadata

from .csv_connector import CsvConnector
from .json_connector import JsonConnector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("connector-svc")


async def process(env: dict[str, Any]) -> dict[str, Any]:
    request_id = env["request_id"]
    fmt = env.get("format", "json")
    source = env.get("source") or ""
    device = env.get("device")

    metadata = SourceMetadata(source_name=source, format=fmt, device=device)

    if fmt == "csv":
        if not isinstance(env.get("data"), str):
            raise ValueError("format='csv' requires data to be raw CSV text.")
        suffix = ".csv"
    else:
        suffix = ".json"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8", newline=""
    ) as tmp:
        if fmt == "csv":
            tmp.write(env["data"])
        else:
            _json.dump(env["data"], tmp)
        tmp_path = Path(tmp.name)

    try:
        connector = CsvConnector(metadata) if fmt == "csv" else JsonConnector(metadata)
        records: list[dict[str, Any]] = []
        for _meta, record in connector.read(tmp_path):
            records.append(record)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    logger.info("[%s] connector emitted %d records (format=%s)", request_id, len(records), fmt)
    return {
        "request_id": request_id,
        "yaml": env["yaml"],
        "metadata": {
            "source_name": metadata.source_name,
            "format": metadata.format,
            "device": metadata.device,
        },
        "records": records,
    }


async def main() -> None:
    await run_worker(
        name="connector",
        in_topic=TOPIC_REQUESTS,
        out_topic=TOPIC_CONNECTOR_OUT,
        group_id=GROUP_CONNECTOR,
        process=process,
        error_topic=TOPIC_RESULTS,
    )


if __name__ == "__main__":
    asyncio.run(main())

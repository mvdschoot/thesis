"""Thin aiokafka wrappers used by every worker + the gateway.

JSON serialization, UTF-8 keys, retry-on-connect for slow Kafka boots.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

logger = logging.getLogger(__name__)

# Bumped above the default 1MB so large CSV → events batches fit comfortably.
MAX_BYTES = 16 * 1024 * 1024


def bootstrap_servers() -> str:
    return os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")


def _serialize(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _deserialize(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


async def make_producer() -> AIOKafkaProducer:
    """Connect a producer with exponential backoff while Kafka is booting."""
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(8):
        producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers(),
            value_serializer=_serialize,
            key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
            max_request_size=MAX_BYTES,
            compression_type="gzip",
        )
        try:
            await producer.start()
            return producer
        except KafkaConnectionError as e:
            last_exc = e
            logger.warning("Kafka producer connect failed (attempt %d): %s", attempt + 1, e)
            await producer.stop()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15.0)
    raise RuntimeError(f"Could not connect Kafka producer after retries: {last_exc}")


async def make_consumer(*topics: str, group_id: str, auto_offset_reset: str = "earliest") -> AIOKafkaConsumer:
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(8):
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers(),
            group_id=group_id,
            value_deserializer=_deserialize,
            key_deserializer=lambda b: b.decode("utf-8") if b is not None else None,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,
            max_partition_fetch_bytes=MAX_BYTES,
        )
        try:
            await consumer.start()
            return consumer
        except KafkaConnectionError as e:
            last_exc = e
            logger.warning("Kafka consumer connect failed (attempt %d): %s", attempt + 1, e)
            await consumer.stop()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15.0)
    raise RuntimeError(f"Could not connect Kafka consumer after retries: {last_exc}")


async def run_worker(
    *,
    name: str,
    in_topic: str,
    out_topic: str | None,
    group_id: str,
    process: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]],
    error_topic: str | None = None,
) -> None:
    """Generic stage worker loop.

    Consumes from `in_topic`, calls `process(envelope)` and publishes the
    result to `out_topic`. On exception, publishes an `error` envelope to
    `error_topic` (typically the final results topic so the gateway resolves
    its pending future immediately) and continues.

    Offsets are committed only AFTER a successful produce — at-least-once.
    """
    logger.info("[%s] starting worker on %s -> %s", name, in_topic, out_topic)
    consumer = await make_consumer(in_topic, group_id=group_id)
    producer = await make_producer()
    try:
        async for msg in consumer:
            env = msg.value
            request_id = (env or {}).get("request_id", "?")
            try:
                result = await process(env)
                if out_topic and result is not None:
                    await producer.send_and_wait(out_topic, result, key=request_id)
            except Exception as e:
                logger.exception("[%s] request %s failed", name, request_id)
                if error_topic:
                    err_env = {
                        "request_id": request_id,
                        "error": {"stage": name, "message": str(e)},
                    }
                    try:
                        await producer.send_and_wait(error_topic, err_env, key=request_id)
                    except Exception:
                        logger.exception("[%s] failed to publish error envelope", name)
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()

"""Harmonia API gateway.

HTTP-facing FastAPI app. The pipeline lives across five Kafka-connected
worker services; this gateway:
  - accepts /api/transform, produces a request envelope to Kafka, awaits a
    matching result envelope, and returns it as JSON;
  - serves /api/configs/* and /api/generate-config (LLM) directly — they
    are not pipeline stages and live here for simplicity.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

import yaml
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.adapter.config_adapter import ConfigAdapter
from shared.envelopes import (
    GROUP_GATEWAY,
    TOPIC_REQUESTS,
    TOPIC_RESULTS,
)
from shared.kafka_io import make_consumer, make_producer

from . import configs_store
from .configs_store import ConfigPayload, ConfigStoreError, ConfigSummary
from .llm.client import LLMClient
from .llm.langchain_client import LangChainClient
from .pending import PendingRegistry
from .prompts import build_system_prompt, build_user_prompt, strip_code_fence

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TRANSFORM_TIMEOUT_SECONDS = float(os.environ.get("TRANSFORM_TIMEOUT_SECONDS", "60"))


# ─── Pydantic request/response models (unchanged from monolith) ─────────────

class GenerateConfigRequest(BaseModel):
    data: Any
    description: str = ""
    hints: str | None = None
    source: str | None = None


class GenerateConfigResponse(BaseModel):
    id: str
    yaml: str


class UpdateConfigRequest(BaseModel):
    yaml: str


class MatchConfigsRequest(BaseModel):
    data: Any
    source: str | None = None


class ConfigMatchAdapterInfo(BaseModel):
    id: str | None = None
    description: str | None = None
    version: str | None = None


class ConfigMatch(BaseModel):
    id: str
    adapter: ConfigMatchAdapterInfo
    source: str | None = None
    source_match: bool
    source_match_known: bool
    matched_records: int
    total_records: int
    applicable: bool
    error: str | None = None


class TransformRequest(BaseModel):
    data: Any
    yaml: str = Field(..., description="The YAML config to run against the data")
    source: str | None = None
    device: str | None = None
    format: Literal["json", "csv"] = "json"


class TransformResponse(BaseModel):
    events: list[dict[str, Any]]
    stats: dict[str, Any]


# ─── Lifespan: Kafka producer + background results consumer ─────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    pending = PendingRegistry()
    producer = await make_producer()
    consumer = await make_consumer(
        TOPIC_RESULTS,
        group_id=f"{GROUP_GATEWAY}-{uuid.uuid4().hex[:8]}",
        auto_offset_reset="latest",
    )

    async def _consume_results() -> None:
        try:
            async for msg in consumer:
                env = msg.value or {}
                rid = env.get("request_id")
                if rid:
                    await pending.resolve(rid, env)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("results consumer crashed")

    consumer_task = asyncio.create_task(_consume_results())

    app.state.producer = producer
    app.state.pending = pending

    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        await consumer.stop()
        await producer.stop()


app = FastAPI(title="Harmonia API Gateway", version="0.2.0", lifespan=lifespan)

allowed = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api")


def _get_llm_client() -> LLMClient:
    return LangChainClient()


# ─── /healthz ───────────────────────────────────────────────────────────────

@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


# ─── /generate-config (unchanged) ───────────────────────────────────────────

@router.post("/generate-config", response_model=GenerateConfigResponse)
def generate_config(req: GenerateConfigRequest) -> GenerateConfigResponse:
    try:
        client = _get_llm_client()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    system = build_system_prompt()
    user = build_user_prompt(
        description=req.description,
        hints=req.hints,
        data=req.data,
        source=req.source,
    )

    try:
        raw = client.generate(system=system, user=user)
    except Exception as e:
        logger.exception("LLM generation failed")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    yaml_text = strip_code_fence(raw)

    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid YAML: {e}")

    try:
        saved = configs_store.save_new_config(yaml_text)
    except ConfigStoreError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned unusable config: {e}")

    return GenerateConfigResponse(id=saved.id, yaml=saved.yaml)


# ─── /configs CRUD (unchanged) ──────────────────────────────────────────────

@router.get("/configs", response_model=list[ConfigSummary])
def list_configs_endpoint() -> list[ConfigSummary]:
    return configs_store.list_configs()


@router.get("/configs/{config_id}", response_model=ConfigPayload)
def get_config_endpoint(config_id: str) -> ConfigPayload:
    try:
        return configs_store.get_config(config_id)
    except ConfigStoreError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.put("/configs/{config_id}", response_model=ConfigPayload)
def update_config_endpoint(config_id: str, req: UpdateConfigRequest) -> ConfigPayload:
    try:
        return configs_store.update_config(config_id, req.yaml)
    except ConfigStoreError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/configs/match", response_model=list[ConfigMatch])
def match_configs_endpoint(req: MatchConfigsRequest) -> list[ConfigMatch]:
    from shared.models import SourceMetadata

    records = _records_from_data(req.data)
    total = len(records)
    source_known = bool(req.source and req.source.strip())

    results: list[ConfigMatch] = []
    for config_id, parsed in configs_store.load_parsed_configs():
        adapter_block = parsed.get("adapter") or {}
        match_block = parsed.get("match") or {}
        config_source = match_block.get("source")
        info = ConfigMatchAdapterInfo(
            id=adapter_block.get("id"),
            description=adapter_block.get("description"),
            version=adapter_block.get("version"),
        )

        try:
            adapter = ConfigAdapter.from_dict(parsed)
        except (KeyError, ValueError) as e:
            results.append(
                ConfigMatch(
                    id=config_id,
                    adapter=info,
                    source=config_source,
                    source_match=False,
                    source_match_known=source_known,
                    matched_records=0,
                    total_records=total,
                    applicable=False,
                    error=f"Invalid config: {e}",
                )
            )
            continue

        if source_known:
            source_match = req.source == config_source
            metadata = SourceMetadata(source_name=req.source or "", format="json")
        else:
            source_match = True
            metadata = SourceMetadata(source_name=config_source or "", format="json")

        matched = 0
        if source_match:
            for record in records:
                if isinstance(record, dict) and adapter.can_handle(metadata, record):
                    matched += 1

        applicable = source_match and matched > 0
        results.append(
            ConfigMatch(
                id=config_id,
                adapter=info,
                source=config_source,
                source_match=source_match,
                source_match_known=source_known,
                matched_records=matched,
                total_records=total,
                applicable=applicable,
            )
        )

    results.sort(key=lambda r: (not r.applicable, -r.matched_records, r.id))
    return results


def _records_from_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


# ─── /transform (Kafka produce-and-await) ───────────────────────────────────

@router.post("/transform", response_model=TransformResponse)
async def transform(req: TransformRequest) -> TransformResponse:
    # Validate config now so a malformed YAML rejects early with HTTP 400 —
    # mirrors the old monolith's behaviour.
    try:
        config = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="YAML must be a mapping at the top level.")
    try:
        ConfigAdapter.from_dict(config)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Config is missing required sections: {e}")

    request_id = str(uuid.uuid4())
    pending: PendingRegistry = app.state.pending
    future = await pending.register(request_id)

    envelope = {
        "request_id": request_id,
        "yaml": req.yaml,
        "data": req.data,
        "format": req.format,
        "source": req.source,
        "device": req.device,
    }

    try:
        await app.state.producer.send_and_wait(TOPIC_REQUESTS, envelope, key=request_id)
    except Exception as e:
        await pending.cancel(request_id)
        logger.exception("Failed to enqueue transform request")
        raise HTTPException(status_code=500, detail=f"Failed to enqueue: {e}")

    try:
        result = await asyncio.wait_for(future, timeout=TRANSFORM_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await pending.cancel(request_id)
        raise HTTPException(
            status_code=504,
            detail=f"Pipeline did not respond within {TRANSFORM_TIMEOUT_SECONDS}s.",
        )

    if "error" in result:
        err = result["error"]
        raise HTTPException(
            status_code=400,
            detail=f"[{err.get('stage', '?')}] {err.get('message', 'unknown error')}",
        )

    return TransformResponse(
        events=result.get("events", []),
        stats=result.get("stats", {}),
    )


app.include_router(router)

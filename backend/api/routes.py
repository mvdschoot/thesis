from __future__ import annotations

import json
import logging
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import configs_store
from api.configs_store import ConfigPayload, ConfigStoreError, ConfigSummary
from api.llm.client import LLMClient
from api.llm.langchain_client import LangChainClient
from api.prompts import build_system_prompt, build_user_prompt, strip_code_fence
from src.adapters.config_adapter import ConfigAdapter
from src.adapters.registry import AdapterRegistry
from src.connectors.base import SourceMetadata
from src.connectors.json_connector import JsonConnector
from src.pipeline import Pipeline

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _get_llm_client() -> LLMClient:
    return LangChainClient()


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


class TransformResponse(BaseModel):
    events: list[dict[str, Any]]
    stats: dict[str, Any]


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


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
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned invalid YAML: {e}",
        )

    try:
        saved = configs_store.save_new_config(yaml_text)
    except ConfigStoreError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned unusable config: {e}")

    return GenerateConfigResponse(id=saved.id, yaml=saved.yaml)


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
            # Source unknown: assume source matches so we can still evaluate
            # the record-level filters, then label the result accordingly.
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


@router.post("/transform", response_model=TransformResponse)
def transform(req: TransformRequest) -> TransformResponse:
    try:
        config = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="YAML must be a mapping at the top level.")

    try:
        adapter = ConfigAdapter.from_dict(config)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Config is missing required sections: {e}")

    registry = AdapterRegistry()
    registry.register(adapter)

    source_name = req.source or config.get("match", {}).get("source", "")
    metadata = SourceMetadata(
        source_name=source_name,
        format="json",
        device=req.device,
    )
    connector = JsonConnector(metadata)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(req.data, tmp)
        tmp_path = Path(tmp.name)

    try:
        pipeline = Pipeline(connector, registry)
        events = pipeline.run(tmp_path)
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=400, detail=f"Transform failed: {e}")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    event_dicts = [e.to_dict() for e in events]

    flag_counter: Counter[str] = Counter()
    subjects: set[str] = set()
    for ev in event_dicts:
        subjects.add(ev.get("subject_id", ""))
        for f in (ev.get("quality") or {}).get("flags", []) or []:
            code = f.get("code")
            if code:
                flag_counter[code] += 1

    stats = {
        "count": len(event_dicts),
        "subjects": sorted(s for s in subjects if s),
        "flags": dict(flag_counter),
    }
    return TransformResponse(events=event_dicts, stats=stats)

"""HTTP route handlers.

`/api/transform` invokes the in-process pipeline directly — no message bus,
no request-id correlation, no timeout. The other routes are thin shims over
the LLM client and configs_store.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query

from domain.models import SourceMetadata
from pipeline import connector, run_pipeline
from pipeline.adapter.config_adapter import ConfigAdapter

from . import configs_store
from .configs_store import ConfigPayload, ConfigStoreError, ConfigSummary
from .llm.client import LLMClient
from .llm.langchain_client import LangChainClient
from .models import (
    ConfigMatch,
    ConfigMatchAdapterInfo,
    GenerateConfigRequest,
    GenerateConfigResponse,
    InputFormat,
    MatchConfigsRequest,
    TerminologySearchResult,
    TransformRequest,
    TransformResponse,
    UpdateConfigRequest,
)
from .prompts import build_system_prompt, build_user_prompt, strip_code_fence
from .terminology import TerminologyError, get_client as get_terminology_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _get_llm_client() -> LLMClient:
    return LangChainClient()


# ─── /healthz ───────────────────────────────────────────────────────────────

@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


# ─── /generate-config ───────────────────────────────────────────────────────

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


# ─── /configs CRUD ──────────────────────────────────────────────────────────

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
    try:
        records = _records_from_data(req.data, req.format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
            metadata = SourceMetadata(source_name=req.source or "", format=req.format)
        else:
            source_match = True
            metadata = SourceMetadata(source_name=config_source or "", format=req.format)

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


def _records_from_data(data: str, format: InputFormat) -> list[dict[str, Any]]:
    """Parse raw input text into a list of record dicts, dispatching by format.

    New formats added under `pipeline.connector` are picked up here as long as
    `connector.run` learns how to dispatch them.
    """
    if format == "json":
        try:
            payload: Any = _json.loads(data)
        except _json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
    elif format == "csv":
        payload = data
    else:
        raise ValueError(f"Unsupported format: {format}")

    _meta, records = connector.run(payload, format=format)
    return records


# ─── /transform (in-process pipeline) ───────────────────────────────────────

@router.post("/transform", response_model=TransformResponse)
def transform(req: TransformRequest) -> TransformResponse:
    # Validate config up-front so a malformed YAML rejects with HTTP 400.
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

    # Pydantic Coding → plain dict so the mapper stage stays framework-agnostic.
    concept_mappings = (
        {k: v.model_dump() for k, v in req.concept_mappings.items()}
        if req.concept_mappings
        else None
    )

    try:
        events, stats = run_pipeline(
            data=req.data,
            yaml_text=req.yaml,
            source=req.source,
            format=req.format,
            device=req.device,
            concept_mappings=concept_mappings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fhir_stats = stats.pop("fhir", None)
    bundle = fhir_stats.get("bundle") if isinstance(fhir_stats, dict) else None
    if isinstance(fhir_stats, dict):
        # Surface counts/size in stats for the UI; the bundle itself moves to
        # a top-level field so the frontend can render it without spelunking.
        stats["fhir.resource_count"] = fhir_stats.get("resource_count", 0)
        stats["fhir.size_bytes"] = fhir_stats.get("size_bytes", 0)

    mapper_stats = stats.pop("mapper", None)
    concept_slots = (
        mapper_stats.get("slots", []) if isinstance(mapper_stats, dict) else []
    )
    if isinstance(mapper_stats, dict):
        stats["mapper.slot_count"] = mapper_stats.get("slot_count", 0)
        stats["mapper.unbound_count"] = mapper_stats.get("unbound_count", 0)

    return TransformResponse(
        events=[e.to_dict() for e in events],
        stats=stats,
        bundle=bundle,
        concept_slots=concept_slots,
    )


# ─── /terminology/search (NLM Clinical Tables proxy) ────────────────────────

@router.get("/terminology/search", response_model=list[TerminologySearchResult])
def terminology_search(
    system: str = Query(..., description="loinc | ucum | snomed"),
    q: str = Query("", description="search terms"),
    max: int = Query(20, ge=1, le=50, description="max results to return"),
) -> list[TerminologySearchResult]:
    sys_norm = (system or "").strip().lower()
    if sys_norm not in ("loinc", "ucum", "snomed"):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported system={system!r}; expected one of: loinc, ucum, snomed",
        )
    if not q.strip():
        return []
    try:
        results = get_terminology_client().search(sys_norm, q, max_results=max)  # type: ignore[arg-type]
    except TerminologyError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return [TerminologySearchResult(**r) for r in results]

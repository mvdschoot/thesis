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
from pipeline import connector, run_pipeline, scan_concepts
from pipeline.adapter.config_adapter import ConfigAdapter

from . import configs_store
from .configs_store import ConfigPayload, ConfigStoreError, ConfigSummary
from .llm.client import LLMClient
from .llm.langchain_client import LangChainClient
from .models import (
    AdapterDiagnosticsOut,
    Coding,
    ConfigMatch,
    ConfigMatchAdapterInfo,
    EditConfigRequest,
    EditConfigResponse,
    GenerateConfigRequest,
    GenerateConfigResponse,
    InputFormat,
    MatchConfigsRequest,
    NoMatchSlot,
    SuggestConceptsRequest,
    SuggestConceptsResponse,
    SuggestFixRequest,
    SuggestFixResponse,
    TerminologySearchResult,
    TransformRequest,
    TransformResponse,
    UpdateConfigRequest,
)
from .prompts import (
    build_concept_suggest_system_prompt,
    build_concept_suggest_user_prompt,
    build_edit_system_prompt,
    build_edit_user_prompt,
    build_fix_system_prompt,
    build_fix_user_prompt,
    build_system_prompt,
    build_user_prompt,
    strip_code_fence,
)
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
        descriptors=req.descriptors,
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
        saved = configs_store.save_new_config(yaml_text, descriptors=req.descriptors)
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

    # ── Concept-scan fast path ──────────────────────────────────────────────
    if req.concept_scan_only:
        try:
            concept_slots, adapter_diagnostics = scan_concepts(
                data=req.data,
                parsed_config=config,
                source=req.source,
                format=req.format,
                device=req.device,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return TransformResponse(
            events=[],
            stats={"count": 0, "subjects": [], "flags": {}},
            bundle=None,
            omop_cdm=None,
            concept_slots=concept_slots,
            adapter_diagnostics=AdapterDiagnosticsOut.model_validate(
                adapter_diagnostics.to_dict()
            ),
        )

    # ── Full pipeline ─────────────────────────────────────────────────────
    # Pydantic Coding → plain dict so the mapper stage stays framework-agnostic.
    concept_mappings = (
        {k: v.model_dump() for k, v in req.concept_mappings.items()}
        if req.concept_mappings
        else None
    )

    try:
        events, stats, adapter_diagnostics = run_pipeline(
            data=req.data,
            parsed_config=config,
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
        stats["fhir.resource_count"] = fhir_stats.get("resource_count", 0)
        stats["fhir.size_bytes"] = fhir_stats.get("size_bytes", 0)

    omop_raw = stats.pop("omop", None)
    omop_cdm = omop_raw if isinstance(omop_raw, dict) else None
    if isinstance(omop_cdm, dict):
        omop_table_stats = omop_cdm.get("stats", {})
        stats["omop.measurement_count"] = omop_table_stats.get("measurement_count", 0)
        stats["omop.observation_count"] = omop_table_stats.get("observation_count", 0)
        stats["omop.unmapped_count"] = omop_table_stats.get("unmapped_count", 0)

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
        omop_cdm=omop_cdm,
        concept_slots=concept_slots,
        adapter_diagnostics=AdapterDiagnosticsOut.model_validate(
            adapter_diagnostics.to_dict()
        ),
    )


# ─── /suggest-config-fix ────────────────────────────────────────────────────

@router.post("/suggest-config-fix", response_model=SuggestFixResponse)
def suggest_config_fix(req: SuggestFixRequest) -> SuggestFixResponse:
    """LLM-patch a failing adapter config given diagnostics + a sample record.

    Same client/few-shot corpus as `/api/generate-config`; the system prompt
    differs only in framing (repair vs. generate). Does NOT save the result —
    the frontend previews the patched YAML and lets the user decide before
    applying it to the editor.
    """
    try:
        client = _get_llm_client()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    system = build_fix_system_prompt()
    user = build_fix_user_prompt(
        yaml_text=req.yaml,
        diagnostics=req.diagnostics.model_dump(),
        sample_record=req.sample_record,
        description=req.description,
    )

    try:
        raw = client.generate(system=system, user=user)
    except Exception as e:
        logger.exception("LLM fix-suggestion failed")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    yaml_text = strip_code_fence(raw)
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid YAML: {e}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="LLM returned non-mapping YAML.")
    try:
        ConfigAdapter.from_dict(parsed)
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned a YAML missing required sections: {e}",
        )

    return SuggestFixResponse(yaml=yaml_text)


# ─── /edit-config ────────────────────────────────────────────────────────────

@router.post("/edit-config", response_model=EditConfigResponse)
def edit_config(req: EditConfigRequest) -> EditConfigResponse:
    """LLM-edit an adapter config from a natural-language instruction.

    Same client/few-shot corpus as `/api/generate-config`; the LLM applies the
    user's requested change and returns the full updated YAML. Does NOT save —
    the frontend previews a diff and lets the user apply it to the editor.
    """
    if not req.yaml or not req.yaml.strip():
        raise HTTPException(status_code=400, detail="No YAML config provided.")
    if not req.instruction or not req.instruction.strip():
        raise HTTPException(status_code=400, detail="No edit instruction provided.")

    try:
        client = _get_llm_client()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    system = build_edit_system_prompt()
    user = build_edit_user_prompt(
        yaml_text=req.yaml,
        instruction=req.instruction,
        sample_data=req.sample_data,
        source=req.source,
    )

    try:
        raw = client.generate(system=system, user=user)
    except Exception as e:
        logger.exception("LLM edit failed")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    yaml_text = strip_code_fence(raw)
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid YAML: {e}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="LLM returned non-mapping YAML.")
    try:
        ConfigAdapter.from_dict(parsed)
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned a YAML missing required sections: {e}",
        )

    return EditConfigResponse(yaml=yaml_text)


# ─── /terminology/search (NLM Clinical Tables proxy) ────────────────────────

@router.get("/terminology/search", response_model=list[TerminologySearchResult])
def terminology_search(
    system: str = Query(..., description="loinc | ucum | snomed | rxnorm | icd10 | cpt"),
    q: str = Query("", description="search terms"),
    max: int = Query(20, ge=1, le=50, description="max results to return"),
) -> list[TerminologySearchResult]:
    sys_norm = (system or "").strip().lower()
    if sys_norm not in ("loinc", "ucum", "snomed", "rxnorm", "icd10", "cpt"):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported system={system!r}; expected one of: loinc, ucum, snomed, rxnorm, icd10, cpt",
        )
    if not q.strip():
        return []
    try:
        results = get_terminology_client().search(sys_norm, q, max_results=max)  # type: ignore[arg-type]
    except TerminologyError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return [TerminologySearchResult(**r) for r in results]


# ─── /suggest-concepts (LLM-driven terminology mapping) ───────────────────

@router.post("/suggest-concepts", response_model=SuggestConceptsResponse)
def suggest_concepts(req: SuggestConceptsRequest) -> SuggestConceptsResponse:
    """Use the LLM + OmopHub tool calling to suggest terminology codes for concept slots."""
    non_category = [s for s in req.slots if s.kind != "category"]
    if not non_category:
        return SuggestConceptsResponse()

    valid_keys = {s.key for s in non_category}
    slot_dicts = [s.model_dump() for s in non_category]

    try:
        client = LangChainClient()
    except RuntimeError as e:
        return SuggestConceptsResponse(errors=[f"LLM unavailable: {e}"])

    from .llm.tools import search_terminology as _raw_search_tool

    seen_codes: set[tuple[str, str]] = set()
    seen_standard: dict[tuple[str, str], str | None] = {}

    from langchain_core.tools import tool as _tool_decorator

    @_tool_decorator
    def search_terminology(searches: list[dict[str, str]]) -> str:
        """Search medical terminology databases for standard codes.

        Submit ALL lookups in a SINGLE call. Up to 25 searches per call.

        Args:
            searches: list of {query, system} objects.
                system: "loinc", "ucum", "snomed", "rxnorm", "icd10", or "cpt".
                query: Natural-language search terms, or a code number to validate.

        Returns:
            JSON list of {query, system, results} in the same order as input.
        """
        result = _raw_search_tool.invoke({"searches": searches})
        try:
            items = _json.loads(result)
            if isinstance(items, list):
                for group in items:
                    if isinstance(group, dict):
                        for item in group.get("results", []):
                            if isinstance(item, dict) and item.get("code"):
                                key_tuple = (item.get("system", ""), item["code"])
                                seen_codes.add(key_tuple)
                                seen_standard[key_tuple] = item.get("standard_concept")
        except _json.JSONDecodeError:
            pass
        return result

    system = build_concept_suggest_system_prompt()
    user = build_concept_suggest_user_prompt(slot_dicts)

    errors: list[str] = []
    try:
        raw = client.generate_with_tools(system, user, tools=[search_terminology])
    except Exception as e:
        logger.exception("LLM concept suggestion failed")
        return SuggestConceptsResponse(errors=[f"LLM error: {e}"])

    raw = raw.strip()
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        if first_nl != -1:
            raw = raw[first_nl + 1:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError:
        return SuggestConceptsResponse(errors=["LLM returned unparseable response."])

    if not isinstance(parsed, dict):
        return SuggestConceptsResponse(errors=["LLM returned non-object response."])

    print("LLM suggestiuons:", parsed)

    if "suggestions" in parsed and isinstance(parsed["suggestions"], dict):
        raw_suggestions = parsed["suggestions"]
        raw_no_matches = parsed.get("no_matches", {})
        if not isinstance(raw_no_matches, dict):
            raw_no_matches = {}
    else:
        raw_suggestions = parsed
        raw_no_matches = {}

    suggestions: dict[str, Coding] = {}
    for key, val in raw_suggestions.items():
        if key not in valid_keys:
            continue
        if not isinstance(val, dict):
            continue
        if not val.get("system") or not val.get("code"):
            continue
        confidence = val.get("confidence")
        if confidence not in ("high", "medium", "low"):
            confidence = None
        sc = seen_standard.get((val["system"], val["code"]))
        suggestions[key] = Coding(
            system=val["system"],
            code=val["code"],
            display=val.get("display"),
            confidence=confidence,
            standard_concept=sc if sc in ("S", "C") else None,
        )

    hallucinated = [
        k for k, c in suggestions.items()
        if (c.system, c.code) not in seen_codes
    ]
    for k in hallucinated:
        logger.warning("Dropping hallucinated code %s for slot %s", suggestions[k].code, k)
        del suggestions[k]

    no_matches: dict[str, NoMatchSlot] = {}
    for key, val in raw_no_matches.items():
        if key not in valid_keys:
            continue
        if not isinstance(val, dict):
            continue
        no_matches[key] = NoMatchSlot(reason=val.get("reason", "No standard code found."))

    if len(suggestions) + len(no_matches) < len(non_category):
        unmapped = len(non_category) - len(suggestions) - len(no_matches)
        errors.append(f"{unmapped} slot(s) could not be mapped automatically.")

    return SuggestConceptsResponse(suggestions=suggestions, no_matches=no_matches, errors=errors)

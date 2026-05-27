"""Pydantic request/response models for the HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

type InputFormat = Literal["json"] | Literal["csv"]

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
    data: str
    format: InputFormat
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


class Coding(BaseModel):
    """One FHIR-shaped Coding picked by the user."""
    system: str
    code: str
    display: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    concept_id: int | None = None


class ConceptSlot(BaseModel):
    """A group of events that share a coding target — user picks once per slot."""
    key: str
    kind: Literal["code", "unit", "component", "category"]
    label: str
    count: int
    sample: dict[str, Any]
    suggested_system: str | None = None
    default_coding: Coding | None = None
    current_mapping: Coding | None = None


class TransformRequest(BaseModel):
    data: Any
    yaml: str = Field(..., description="The YAML config to run against the data")
    source: str | None = None
    device: str | None = None
    format: Literal["json", "csv"] = "json"
    concept_mappings: dict[str, Coding] | None = Field(
        default=None,
        description=(
            "User-picked codings keyed by slot. See pipeline.mapper.keys for the "
            "key scheme (code|... / unit|... / component|... / category|...)."
        ),
    )
    concept_scan_only: bool = Field(
        default=False,
        description="Only discover concept slots (skip cleaning, validation, qualification, FHIR, OMOP).",
    )


class SkippedReasonOut(BaseModel):
    """One reason a record (or part of it) failed to produce an event in the
    adapter stage. Surfaced to the UI so the user can fix the LLM-generated
    YAML config."""
    code: str
    record_index: int
    detail: str
    rule_id: str | None = None
    path: str | None = None
    expected: Any = None
    actual: Any = None
    record_keys: list[str] | None = None


class RuleDiagnosticOut(BaseModel):
    rule_id: str
    records_seen: int
    events_emitted: int
    skipped_reasons: list[SkippedReasonOut] = Field(default_factory=list)


class AdapterDiagnosticsOut(BaseModel):
    records_total: int
    records_matched: int
    records_unmatched: int
    events_emitted: int
    rules: list[RuleDiagnosticOut] = Field(default_factory=list)
    predicate_failures: list[SkippedReasonOut] = Field(default_factory=list)


class TransformResponse(BaseModel):
    events: list[dict[str, Any]]
    stats: dict[str, Any]
    bundle: dict[str, Any] | None = None
    omop_cdm: dict[str, Any] | None = None
    concept_slots: list[ConceptSlot] = Field(default_factory=list)
    adapter_diagnostics: AdapterDiagnosticsOut | None = None


class SuggestFixRequest(BaseModel):
    yaml: str = Field(..., description="The current (failing) YAML config.")
    diagnostics: AdapterDiagnosticsOut = Field(
        ..., description="Diagnostics from the most recent /api/transform call."
    )
    sample_record: Any = Field(
        ..., description="One record from the input that the config failed on."
    )
    description: str = Field(
        default="",
        description="Optional free-text describing the data/source for the LLM.",
    )


class SuggestFixResponse(BaseModel):
    yaml: str


class SuggestConceptsRequest(BaseModel):
    slots: list[ConceptSlot]


class NoMatchSlot(BaseModel):
    """A concept slot where the LLM determined no standard code exists."""
    reason: str


class SuggestConceptsResponse(BaseModel):
    suggestions: dict[str, Coding] = Field(default_factory=dict)
    no_matches: dict[str, NoMatchSlot] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class TerminologySearchResult(BaseModel):
    system: str
    code: str
    display: str
    concept_id: int | None = None

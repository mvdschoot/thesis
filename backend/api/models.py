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


class TransformResponse(BaseModel):
    events: list[dict[str, Any]]
    stats: dict[str, Any]
    bundle: dict[str, Any] | None = None
    concept_slots: list[ConceptSlot] = Field(default_factory=list)


class TerminologySearchResult(BaseModel):
    system: str
    code: str
    display: str

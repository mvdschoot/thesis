"""Domain types shared across every service.

CanonicalEvent (and its constituent enums + dataclasses) are the contract
between every pipeline stage. SourceMetadata describes where a record came
from and is propagated by the connector → adapter chain. Everything else
(connector implementations, adapters, validators, etc.) is owned by its
respective service module.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ─── SourceMetadata (was src/connectors/base.py) ────────────────────────────

@dataclass
class SourceMetadata:
    """Describes the data source a connector is reading from."""

    source_name: str          # e.g., "fitbit", "withings", "redcap"
    format: str               # e.g., "json", "csv", "xlsx"
    device: str | None = None # e.g., "Fitbit Charge 6"
    modality: str = "unknown" # e.g., "wearable", "survey", "sensor"
    description: str = ""     # free-text description of the data


# ─── Enums ──────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    MEASUREMENT = "measurement"
    OBSERVATION = "observation"
    SURVEY = "survey"
    EVENT = "event"
    SUMMARY = "summary"
    SESSION = "session"


class Granularity(str, Enum):
    INSTANT = "instant"
    INTERVAL = "interval"
    DAILY = "daily"
    SESSION = "session"
    UNKNOWN = "unknown"


class Modality(str, Enum):
    WEARABLE = "wearable"
    SCALE = "scale"
    SURVEY = "survey"
    SENSOR = "sensor"
    APP = "app"
    GAME = "game"
    VR = "vr"
    UNKNOWN = "unknown"


class Stage(str, Enum):
    RAW = "raw"
    STRUCTURED = "structured"
    CLEANED = "cleaned"
    VALIDATED = "validated"
    QUALIFIED = "qualified"
    MAPPED = "mapped"
    STANDARDIZED = "standardized"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MappingMethod(str, Enum):
    RULE = "rule"
    TERMINOLOGY_LOOKUP = "terminology-lookup"
    AI = "ai"
    MANUAL = "manual"


class StandardSystem(str, Enum):
    LOINC = "LOINC"
    SNOMED_CT = "SNOMED-CT"
    UCUM = "UCUM"
    CUSTOM = "custom"


# ─── Event sub-objects ──────────────────────────────────────────────────────

@dataclass
class Component:
    name: str
    value: Any
    unit: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "unit": self.unit}


@dataclass
class Payload:
    raw_value: Any
    value: int | float | str | bool | None = None
    unit: str | None = None
    label: str | None = None
    components: list[Component] | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "raw_value": self.raw_value,
            "value": self.value,
            "unit": self.unit,
            "label": self.label,
        }
        if self.components is not None:
            d["components"] = [c.to_dict() for c in self.components]
        else:
            d["components"] = None
        return d


@dataclass
class Context:
    source: str
    modality: Modality
    device: str | None = None
    source_measurement_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "modality": self.modality.value,
            "device": self.device,
            "source_measurement_type": self.source_measurement_type,
        }


@dataclass
class Provenance:
    source_record_id: str
    ingested_at: str
    group_id: str | None = None
    parent_event_id: str | None = None
    adapter: str | None = None
    adapter_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_record_id": self.source_record_id,
            "ingested_at": self.ingested_at,
            "group_id": self.group_id,
            "parent_event_id": self.parent_event_id,
            "adapter": self.adapter,
            "adapter_version": self.adapter_version,
        }


@dataclass
class Mapping:
    standard_code: str | None = None
    standard_system: str | None = None
    standard_display: str | None = None
    confidence: float | None = None
    method: str | None = None

    def to_dict(self) -> dict:
        return {
            "standard_code": self.standard_code,
            "standard_system": self.standard_system,
            "standard_display": self.standard_display,
            "confidence": self.confidence,
            "method": self.method,
        }


@dataclass
class QualityFlag:
    code: str
    severity: Severity
    stage: str
    message: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "stage": self.stage,
            "message": self.message,
        }


@dataclass
class Quality:
    flags: list[QualityFlag] = field(default_factory=list)
    conformance: str | None = None
    completeness: float | None = None
    plausibility: str | None = None
    expected_field_count: int | None = None
    present_field_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "flags": [f.to_dict() for f in self.flags],
            "conformance": self.conformance,
            "completeness": self.completeness,
            "plausibility": self.plausibility,
            "expected_field_count": self.expected_field_count,
            "present_field_count": self.present_field_count,
        }


# ─── CanonicalEvent ─────────────────────────────────────────────────────────

@dataclass
class CanonicalEvent:
    event_id: str
    subject_id: str
    timestamp: str
    type: EventType
    category: str
    payload: Payload
    context: Context
    provenance: Provenance
    mapping: Mapping
    quality: Quality
    stage: Stage
    timestamp_end: str | None = None
    duration_seconds: float | None = None
    granularity: Granularity = Granularity.UNKNOWN
    extensions: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        # Strip internal extension keys (leading underscore) — they're plumbing
        # for cross-stage hand-off (e.g., "_quality_override") and not part of
        # the user-facing canonical event.
        public_extensions: dict[str, Any] | None
        if self.extensions is None:
            public_extensions = None
        else:
            public_extensions = {
                k: v for k, v in self.extensions.items() if not str(k).startswith("_")
            } or None
        return {
            "event_id": self.event_id,
            "subject_id": self.subject_id,
            "timestamp": self.timestamp,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": self.duration_seconds,
            "type": self.type.value,
            "category": self.category,
            "granularity": self.granularity.value,
            "payload": self.payload.to_dict(),
            "context": self.context.to_dict(),
            "provenance": self.provenance.to_dict(),
            "mapping": self.mapping.to_dict(),
            "quality": self.quality.to_dict(),
            "stage": self.stage.value,
            "extensions": public_extensions,
        }

    def has_severity(self, severity: Severity) -> bool:
        return any(f.severity == severity for f in self.quality.flags)

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

    @classmethod
    def from_dict(cls, data: dict) -> "CanonicalEvent":
        """Reconstruct a CanonicalEvent from its to_dict() output.

        Used by the Kafka workers to round-trip events between stages
        without losing dataclass typing.
        """
        payload_d = data.get("payload") or {}
        components_d = payload_d.get("components")
        components = (
            [Component(name=c["name"], value=c.get("value"), unit=c.get("unit"))
             for c in components_d]
            if components_d is not None
            else None
        )
        payload = Payload(
            raw_value=payload_d.get("raw_value"),
            value=payload_d.get("value"),
            unit=payload_d.get("unit"),
            label=payload_d.get("label"),
            components=components,
        )

        ctx_d = data.get("context") or {}
        context = Context(
            source=ctx_d.get("source", ""),
            modality=Modality(ctx_d.get("modality", "unknown")),
            device=ctx_d.get("device"),
            source_measurement_type=ctx_d.get("source_measurement_type"),
        )

        prov_d = data.get("provenance") or {}
        provenance = Provenance(
            source_record_id=prov_d.get("source_record_id", ""),
            ingested_at=prov_d.get("ingested_at", ""),
            group_id=prov_d.get("group_id"),
            parent_event_id=prov_d.get("parent_event_id"),
            adapter=prov_d.get("adapter"),
            adapter_version=prov_d.get("adapter_version"),
        )

        map_d = data.get("mapping") or {}
        mapping = Mapping(
            standard_code=map_d.get("standard_code"),
            standard_system=map_d.get("standard_system"),
            standard_display=map_d.get("standard_display"),
            confidence=map_d.get("confidence"),
            method=map_d.get("method"),
        )

        q_d = data.get("quality") or {}
        flags = [
            QualityFlag(
                code=f["code"],
                severity=Severity(f["severity"]),
                stage=f.get("stage", ""),
                message=f.get("message"),
            )
            for f in (q_d.get("flags") or [])
        ]
        quality = Quality(
            flags=flags,
            conformance=q_d.get("conformance"),
            completeness=q_d.get("completeness"),
            plausibility=q_d.get("plausibility"),
            expected_field_count=q_d.get("expected_field_count"),
            present_field_count=q_d.get("present_field_count"),
        )

        return cls(
            event_id=data["event_id"],
            subject_id=data.get("subject_id", ""),
            timestamp=data.get("timestamp", ""),
            timestamp_end=data.get("timestamp_end"),
            duration_seconds=data.get("duration_seconds"),
            type=EventType(data["type"]),
            category=data.get("category", "unknown"),
            granularity=Granularity(data.get("granularity", "unknown")),
            payload=payload,
            context=context,
            provenance=provenance,
            mapping=mapping,
            quality=quality,
            stage=Stage(data.get("stage", "structured")),
            extensions=data.get("extensions"),
        )

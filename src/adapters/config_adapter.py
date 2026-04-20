"""Config-driven adapter (Tier 1).

Reads a YAML mapping configuration and transforms source records into
canonical events without any source-specific code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..connectors.base import SourceMetadata
from ..models.canonical import (
    CanonicalEvent,
    Component,
    Context,
    EventType,
    Granularity,
    Mapping,
    Modality,
    Payload,
    Provenance,
    Quality,
    QualityFlag,
    Severity,
    Stage,
)
from .base import BaseAdapter


def _resolve_path(obj: Any, path: str) -> Any:
    """Resolve a dot-notation path with array indexing against a data object.

    Examples:
        "userId"                                        -> obj["userId"]
        "measurementValue.activities-heart[0].value"    -> obj["measurementValue"]["activities-heart"][0]["value"]
        "@item.value"                                   -> handled by caller (item passed as obj)
    """
    if obj is None:
        return None

    parts = re.split(r"\.", path)
    current = obj
    for part in parts:
        if current is None:
            return None
        # Handle array indexing: "key[0]"
        match = re.match(r"^(.+?)\[(\d+)\]$", part)
        if match:
            key, idx = match.group(1), int(match.group(2))
            current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            current = current.get(part) if isinstance(current, dict) else None
    return current


def _apply_transform(value: Any, transform: str) -> Any:
    """Apply a named transform to a value."""
    if value is None:
        return None
    s = str(value)
    if transform == "start_of_day":
        date_part = s[:10]
        return f"{date_part}T00:00:00.000Z"
    elif transform == "end_of_day":
        date_part = s[:10]
        return f"{date_part}T23:59:59.999Z"
    elif transform == "to_int":
        try:
            return int(s)
        except (ValueError, TypeError):
            return None
    elif transform == "to_float":
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    elif transform == "iso_date":
        date_part = s[:10]
        return f"{date_part}T00:00:00.000Z"
    return value


def _resolve_value(
    spec: Any, record: dict[str, Any], item: Any | None = None
) -> Any:
    """Resolve a value specification from the config.

    Handles: literal values, {path}, {path, transform}, {path, fallback},
    {multiply}, {template}, {date_from, time_from}.
    """
    # Literal values (strings, numbers, booleans, None)
    if not isinstance(spec, dict):
        return spec

    # Path resolution
    if "path" in spec:
        path = spec["path"]
        # @item references resolve against the iteration element
        if path.startswith("@item"):
            if item is None:
                return spec.get("fallback")
            if path == "@item":
                obj = item
            else:
                # "@item.field" -> resolve "field" against item
                sub_path = path[len("@item."):]
                obj = _resolve_path(item, sub_path)
            value = obj
        else:
            value = _resolve_path(record, path)

        if value is None and "fallback" in spec:
            value = spec["fallback"]
        if "transform" in spec:
            value = _apply_transform(value, spec["transform"])
        return value

    # Composite timestamp: date_from + time_from
    if "date_from" in spec and "time_from" in spec:
        date_val = _resolve_value(spec["date_from"], record, item)
        time_val = _resolve_value(spec["time_from"], record, item)
        if date_val and time_val:
            date_part = str(date_val)[:10]
            return f"{date_part}T{time_val}Z"
        return None

    # Arithmetic: multiply
    if "multiply" in spec:
        result = 1
        for operand in spec["multiply"]:
            val = _resolve_value(operand, record, item)
            if val is None:
                return None
            result *= float(val)
        return result

    # Template: string interpolation
    if "template" in spec:
        template = spec["template"]

        def replacer(m: re.Match) -> str:
            ref = m.group(1)
            if ref.startswith("@item.") and item is not None:
                v = _resolve_path(item, ref[len("@item."):])
            else:
                v = _resolve_path(record, ref)
            return str(v) if v is not None else ""

        return re.sub(r"\{(.+?)\}", replacer, template)

    return None


class ConfigAdapter(BaseAdapter):
    """A generic adapter driven by a YAML mapping configuration.

    One instance per config file. The config defines the match conditions,
    field mappings, and emit rules.
    """

    def __init__(self, config_path: str | Path) -> None:
        config_path = Path(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        self._adapter_info = self._config["adapter"]
        self._match = self._config["match"]
        self._defaults = self._config.get("defaults", {})
        self._rules = self._config["emit"]

    @property
    def source_type(self) -> str:
        return self._match["source"]

    @property
    def adapter_id(self) -> str:
        return self._adapter_info["id"]

    @property
    def version(self) -> str:
        return self._adapter_info["version"]

    def can_handle(self, metadata: SourceMetadata, record: dict[str, Any]) -> bool:
        if metadata.source_name != self._match["source"]:
            return False
        for condition in self._match.get("record", []):
            field_val = _resolve_path(record, condition["field"])
            if field_val != condition["equals"]:
                return False
        return True

    def transform(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        group_id = CanonicalEvent.new_id()
        ingested_at = CanonicalEvent.now_iso()
        all_events: list[CanonicalEvent] = []
        # Track events by rule id for parent references
        rule_events: dict[str, list[CanonicalEvent]] = {}

        for rule in self._rules:
            rule_id = rule["id"]
            events = self._execute_rule(
                rule, record, metadata, group_id, ingested_at, rule_events
            )
            rule_events[rule_id] = events
            all_events.extend(events)

        return all_events

    def _execute_rule(
        self,
        rule: dict[str, Any],
        record: dict[str, Any],
        metadata: SourceMetadata,
        group_id: str,
        ingested_at: str,
        rule_events: dict[str, list[CanonicalEvent]],
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []

        # Determine parent event id
        parent_id = None
        parent_ref = rule.get("parent")
        if parent_ref and parent_ref in rule_events:
            parent_events = rule_events[parent_ref]
            if parent_events:
                parent_id = parent_events[0].event_id

        # Check for iteration
        iterate_path = rule.get("iterate")
        if iterate_path and not iterate_path.startswith("@"):
            items = _resolve_path(record, iterate_path)
            if isinstance(items, list):
                for item in items:
                    event = self._build_event(
                        rule, record, metadata, group_id, ingested_at, parent_id, item
                    )
                    events.append(event)
        elif "iterate_object" in rule:
            # Object-to-array expansion
            obj_spec = rule["iterate_object"]
            source_obj = _resolve_path(record, obj_spec["source"])
            if isinstance(source_obj, dict):
                for entry in obj_spec["entries"]:
                    key = entry["key"]
                    if key in source_obj:
                        item = {
                            "key": key,
                            "label": entry.get("label", key),
                            "value": source_obj[key],
                        }
                        event = self._build_event(
                            rule, record, metadata, group_id, ingested_at, parent_id, item
                        )
                        events.append(event)
        else:
            # Single event
            event = self._build_event(
                rule, record, metadata, group_id, ingested_at, parent_id, None
            )
            events.append(event)

        return events

    def _build_event(
        self,
        rule: dict[str, Any],
        record: dict[str, Any],
        metadata: SourceMetadata,
        group_id: str,
        ingested_at: str,
        parent_id: str | None,
        item: Any | None,
    ) -> CanonicalEvent:
        # Resolve subject_id
        subject_spec = self._defaults.get("subject_id", {})
        subject_id = _resolve_value(subject_spec, record, item) or ""

        # Resolve timestamp
        ts_spec = rule.get("timestamp", {})
        timestamp = _resolve_value(ts_spec.get("start"), record, item) or ""
        timestamp_end = _resolve_value(ts_spec.get("end"), record, item)
        duration = _resolve_value(ts_spec.get("duration_seconds"), record, item)

        # Resolve payload
        p_spec = rule.get("payload", {})
        value = _resolve_value(p_spec.get("value"), record, item)
        raw_value = _resolve_value(p_spec.get("raw_value"), record, item)
        unit = _resolve_value(p_spec.get("unit"), record, item)
        label = _resolve_value(p_spec.get("label"), record, item)

        # Resolve components
        components = None
        if "components" in p_spec:
            components = []
            for c_spec in p_spec["components"]:
                c_val = _resolve_value(c_spec.get("value"), record, item)
                c_unit = _resolve_value(c_spec.get("unit"), record, item) if "unit" in c_spec else None
                components.append(Component(
                    name=c_spec["name"],
                    value=c_val,
                    unit=c_unit,
                ))

        # Resolve context
        ctx_defaults = self._defaults.get("context", {})
        ctx_source = _resolve_value(ctx_defaults.get("source"), record, item) or self._match["source"]
        ctx_modality_str = _resolve_value(ctx_defaults.get("modality"), record, item) or "unknown"
        ctx_device = _resolve_value(ctx_defaults.get("device"), record, item) or metadata.device
        ctx_smt = _resolve_value(ctx_defaults.get("source_measurement_type"), record, item)

        try:
            ctx_modality = Modality(ctx_modality_str)
        except ValueError:
            ctx_modality = Modality.UNKNOWN

        # Resolve extensions
        extensions = None
        ext_spec = rule.get("extensions")
        if ext_spec:
            extensions = {}
            for key, val_spec in ext_spec.items():
                extensions[key] = _resolve_value(val_spec, record, item)

        # Resolve quality flags
        quality_flags: list[QualityFlag] = []
        q_spec = rule.get("quality", {})
        for flag_spec in q_spec.get("flags", []):
            if "condition" in flag_spec:
                cond = flag_spec["condition"]
                cond_val = _resolve_value({"path": cond["path"]}, record, item)
                if cond_val != cond.get("equals"):
                    continue
            f = flag_spec.get("flag", flag_spec)
            quality_flags.append(QualityFlag(
                code=f.get("code", "UNKNOWN"),
                severity=Severity(f.get("severity", "info")),
                stage=f.get("stage", "structured"),
                message=f.get("message"),
            ))

        # Build provenance
        user_id = _resolve_value({"path": "userId"}, record) or ""
        m_type = _resolve_value({"path": "measurementType"}, record) or ""
        m_dt = _resolve_value({"path": "measurementDateTime"}, record) or ""
        source_record_id = f"{ctx_source}:{user_id}:{m_type}:{m_dt}"

        return CanonicalEvent(
            event_id=CanonicalEvent.new_id(),
            subject_id=str(subject_id),
            timestamp=str(timestamp) if timestamp else "",
            timestamp_end=str(timestamp_end) if timestamp_end else None,
            duration_seconds=float(duration) if duration is not None else None,
            type=EventType(rule["type"]),
            category=rule["category"],
            granularity=Granularity(rule.get("granularity", "unknown")),
            payload=Payload(
                value=value,
                raw_value=raw_value,
                unit=unit,
                label=label,
                components=components,
            ),
            context=Context(
                source=ctx_source,
                modality=ctx_modality,
                device=ctx_device,
                source_measurement_type=ctx_smt,
            ),
            provenance=Provenance(
                source_record_id=source_record_id,
                ingested_at=ingested_at,
                group_id=group_id,
                parent_event_id=parent_id,
                adapter=self.adapter_id,
                adapter_version=self.version,
            ),
            mapping=Mapping(),
            quality=Quality(flags=quality_flags),
            stage=Stage(self._defaults.get("stage", "structured")),
            extensions=extensions,
        )

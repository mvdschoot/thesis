"""Config-driven adapter (Tier 1).

Reads a YAML mapping configuration and transforms source records into
canonical events without any source-specific code.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from domain.coerce import try_coerce_numeric
from domain.models import (
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
    SourceMetadata,
    Stage,
)

from pipeline.cleaner.config import CleanConfig
from pipeline.fhir.config import FhirConfig
from pipeline.omop.config import OmopConfig
from pipeline.qualifier.config import QualifyConfig
from pipeline.validator.config import ValidateConfig

from .base import BaseAdapter
from .diagnostics import DiagnosticsCollector, SkippedReason, top_level_keys

logger = logging.getLogger(__name__)


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
    elif transform == "iso_millis":
        m = re.match(r"^(.*?)(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$", s)
        if not m:
            return value
        head, frac, tz = m.group(1), m.group(2) or "", m.group(3) or ""
        if frac:
            frac = (frac + "000")[:3]
            return f"{head}.{frac}{tz}"
        return f"{head}.000{tz}" if tz or "T" in head else value
    return value


def _parse_timestamp(value: Any, format_str: str) -> Any:
    """Parse a timestamp string with an explicit ``strptime`` format and emit
    ISO 8601 with millisecond precision in UTC.

    Naive parsed values are interpreted as UTC (matches the cleaner's
    TIMEZONE_ASSUMED_UTC convention). Aware values are converted to UTC.
    Returns the original value unchanged on parse failure so the validator
    can flag it downstream.
    """
    if value is None or value == "":
        return value
    try:
        dt = datetime.strptime(str(value), format_str)
    except (ValueError, TypeError) as e:
        logger.warning(
            "parse_timestamp failed: value=%r format=%r error=%s", value, format_str, e
        )
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    millis = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def _resolve_value(
    spec: Any,
    record: dict[str, Any],
    item: Any | None = None,
    *,
    record_index: int | None = None,
) -> Any:
    """Resolve a value specification from the config.

    Handles: literal values, {path}, {path, transform}, {path, fallback},
    {multiply}, {template}, {date_from, time_from}.
    ``@record_index`` resolves to the 0-based row/record number.
    """
    if not isinstance(spec, dict):
        return spec

    if "path" in spec:
        path = spec["path"]
        if path == "@record_index":
            value = record_index if record_index is not None else 0
        elif path.startswith("@item"):
            if item is None:
                return spec.get("fallback")
            if path == "@item":
                obj = item
            else:
                sub_path = path[len("@item."):]
                obj = _resolve_path(item, sub_path)
            value = obj
        else:
            value = _resolve_path(record, path)

        if value is None and "fallback" in spec:
            value = _resolve_value(spec["fallback"], record, item, record_index=record_index)
        if "transform" in spec:
            value = _apply_transform(value, spec["transform"])
        if "parse_timestamp" in spec:
            value = _parse_timestamp(value, spec["parse_timestamp"])
        return value

    if "date_from" in spec and "time_from" in spec:
        date_val = _resolve_value(spec["date_from"], record, item, record_index=record_index)
        time_val = _resolve_value(spec["time_from"], record, item, record_index=record_index)
        if date_val and time_val:
            date_part = str(date_val)[:10]
            return f"{date_part}T{time_val}Z"
        return None

    if "multiply" in spec:
        result = 1
        for operand in spec["multiply"]:
            val = _resolve_value(operand, record, item, record_index=record_index)
            if val is None:
                return None
            result *= float(val)
        return result

    if "template" in spec:
        template = spec["template"]

        def replacer(m: re.Match) -> str:
            ref = m.group(1)
            if ref == "@record_index":
                return str(record_index if record_index is not None else 0)
            if ref.startswith("@item.") and item is not None:
                v = _resolve_path(item, ref[len("@item."):])
            else:
                v = _resolve_path(record, ref)
            return str(v) if v is not None else ""

        rendered = re.sub(r"\{(.+?)\}", replacer, template)
        if "parse_timestamp" in spec:
            rendered = _parse_timestamp(rendered, spec["parse_timestamp"])
        return rendered

    if "lookup" in spec:
        lk = spec["lookup"]
        key_val = _resolve_value(lk["key"], record, item, record_index=record_index)
        mapping = lk.get("map", {})
        if key_val in mapping:
            return mapping[key_val]
        return lk.get("default")

    return None


def _check_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if value is None:
        return False
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return True
        if isinstance(value, str):
            coerced, ok = try_coerce_numeric(value)
            return ok and isinstance(coerced, int) and not isinstance(coerced, bool)
        return False
    if expected == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if isinstance(value, str):
            coerced, ok = try_coerce_numeric(value)
            return ok and isinstance(coerced, (int, float)) and not isinstance(coerced, bool)
        return False
    if expected == "boolean":
        return isinstance(value, bool)
    raise ValueError(f"Unknown match predicate type: {expected!r}")


def _evaluate_predicate(condition: dict[str, Any], record: dict[str, Any]) -> bool:
    """Evaluate one entry of `match.record` against a record.

    Supported verbs (all AND-ed within one entry):
      - equals: X          — exact equality
      - in: [A, B, ...]    — membership
      - exists: true|false — true: value is not None; false: value is None/missing
      - type: "object"|"array"|"string"|"number"|"integer"|"boolean"|"null"
      - non_empty: true    — arrays/strings/objects must have length > 0
    """
    return _explain_predicate(condition, record) is None


def _explain_predicate(
    condition: dict[str, Any], record: dict[str, Any]
) -> tuple[str, Any, Any] | None:
    """Return `(verb, expected, actual)` of the first failing clause, or None
    if the predicate matched. Used both for matching (`_evaluate_predicate`
    delegates here) and for explaining `can_handle` misses to the user.
    """
    field = condition["field"]
    value = _resolve_path(record, field)

    if "equals" in condition and value != condition["equals"]:
        return ("equals", condition["equals"], value)
    if "in" in condition:
        allowed = condition["in"]
        if not isinstance(allowed, list) or value not in allowed:
            return ("in", allowed, value)
    if "exists" in condition:
        must_exist = bool(condition["exists"])
        if must_exist and value is None:
            return ("exists", True, None)
        if not must_exist and value is not None:
            return ("exists", False, value)
    if "type" in condition and not _check_type(value, condition["type"]):
        return ("type", condition["type"], type(value).__name__ if value is not None else "null")
    if condition.get("non_empty"):
        if value is None:
            return ("non_empty", True, None)
        if isinstance(value, (list, str, dict)) and len(value) == 0:
            return ("non_empty", True, value)
    return None


class ConfigAdapter(BaseAdapter):
    """A generic adapter driven by a YAML mapping configuration."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        if config is not None:
            self._config = config
        elif config_path is not None:
            with open(Path(config_path), "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
        else:
            raise ValueError("ConfigAdapter requires either config_path or config")

        self._adapter_info = self._config["adapter"]
        self._match = self._config["match"]
        self._defaults = self._config.get("defaults", {})
        self._rules = self._config["emit"]
        # New optional sibling sections — None when omitted, in which case the
        # corresponding stage falls back to its current default behavior.
        self._clean_block = CleanConfig.from_dict(self._config.get("clean"))
        self._validate_block = ValidateConfig.from_dict(self._config.get("validate"))
        self._qualify_block = QualifyConfig.from_dict(self._config.get("qualify"))
        self._fhir_block = FhirConfig.from_dict(self._config.get("fhir"))
        self._omop_block = OmopConfig.from_dict(self._config.get("omop"))

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "ConfigAdapter":
        return cls(config=config)

    @property
    def source_type(self) -> str:
        return self._match["source"]

    @property
    def adapter_id(self) -> str:
        return self._adapter_info["id"]

    @property
    def version(self) -> str:
        return self._adapter_info["version"]

    @property
    def clean_block(self) -> CleanConfig | None:
        return self._clean_block

    @property
    def validate_block(self) -> ValidateConfig | None:
        return self._validate_block

    @property
    def qualify_block(self) -> QualifyConfig | None:
        return self._qualify_block

    @property
    def fhir_block(self) -> FhirConfig | None:
        return self._fhir_block

    @property
    def omop_block(self) -> OmopConfig | None:
        return self._omop_block

    def can_handle(self, metadata: SourceMetadata, record: dict[str, Any]) -> bool:
        for condition in self._match.get("record", []):
            if not _evaluate_predicate(condition, record):
                return False
        return True

    def explain_no_match(
        self,
        metadata: SourceMetadata,
        record: dict[str, Any],
        record_index: int,
    ) -> SkippedReason | None:
        """Return the first failing match.record clause as a SkippedReason, or
        None if every clause actually matched (shouldn't happen — caller should
        only invoke this after `can_handle` returned False).
        """
        for condition in self._match.get("record", []):
            failure = _explain_predicate(condition, record)
            if failure is not None:
                verb, expected, actual = failure
                return SkippedReason(
                    code="predicate_mismatch",
                    rule_id=None,
                    record_index=record_index,
                    path=condition.get("field"),
                    detail=(
                        f"Record failed match.record clause "
                        f"`{condition.get('field')} {verb} {expected!r}` "
                        f"(actual: {actual!r})."
                    ),
                    expected=expected,
                    actual=actual,
                    record_keys=top_level_keys(record),
                )
        return None

    def transform(
        self,
        metadata: SourceMetadata,
        record: dict[str, Any],
        *,
        record_index: int = 0,
        collector: DiagnosticsCollector | None = None,
    ) -> list[CanonicalEvent]:
        group_id = CanonicalEvent.new_id()
        ingested_at = CanonicalEvent.now_iso()
        all_events: list[CanonicalEvent] = []
        rule_events: dict[str, list[CanonicalEvent]] = {}

        for rule in self._rules:
            rule_id = rule["id"]
            if collector is not None:
                collector.start_rule(rule_id)
            events = self._execute_rule(
                rule, record, metadata, group_id, ingested_at, rule_events,
                record_index=record_index,
                collector=collector,
            )
            if collector is not None:
                collector.end_rule(rule_id, len(events))
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
        *,
        record_index: int = 0,
        collector: DiagnosticsCollector | None = None,
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        rule_id = rule.get("id", "<unnamed>")

        parent_id = None
        parent_ref = rule.get("parent")
        if parent_ref and parent_ref in rule_events:
            parent_events = rule_events[parent_ref]
            if parent_events:
                parent_id = parent_events[0].event_id
            elif collector is not None:
                collector.record_skip(
                    code="parent_rule_empty",
                    detail=(
                        f"Rule '{rule_id}' references parent '{parent_ref}' but "
                        "the parent rule produced 0 events for this record."
                    ),
                    path=parent_ref,
                )

        iterate_path = rule.get("iterate")
        if iterate_path and not iterate_path.startswith("@"):
            items = _resolve_path(record, iterate_path)
            if items is None:
                if collector is not None:
                    collector.record_skip(
                        code="iterate_path_none",
                        detail=(
                            f"Rule '{rule_id}': iterate path '{iterate_path}' "
                            "did not resolve in this record."
                        ),
                        path=iterate_path,
                        record_keys=top_level_keys(record),
                    )
            elif not isinstance(items, list):
                if collector is not None:
                    collector.record_skip(
                        code="iterate_not_list",
                        detail=(
                            f"Rule '{rule_id}': iterate path '{iterate_path}' "
                            f"resolved to {type(items).__name__} (expected array)."
                        ),
                        path=iterate_path,
                        actual=type(items).__name__,
                        expected="array",
                    )
            elif len(items) == 0:
                if collector is not None:
                    collector.record_skip(
                        code="iterate_empty",
                        detail=(
                            f"Rule '{rule_id}': iterate path '{iterate_path}' "
                            "is an empty array."
                        ),
                        path=iterate_path,
                    )
            else:
                for item in items:
                    event = self._build_event(
                        rule, record, metadata, group_id, ingested_at, parent_id, item,
                        record_index=record_index,
                    )
                    events.append(event)
        elif "iterate_object" in rule:
            obj_spec = rule["iterate_object"]
            source_path = obj_spec.get("source")
            source_obj = _resolve_path(record, source_path) if source_path else None
            if source_obj is None:
                if collector is not None:
                    collector.record_skip(
                        code="iterate_object_source_none",
                        detail=(
                            f"Rule '{rule_id}': iterate_object source "
                            f"'{source_path}' did not resolve in this record."
                        ),
                        path=source_path,
                        record_keys=top_level_keys(record),
                    )
            elif not isinstance(source_obj, dict):
                if collector is not None:
                    collector.record_skip(
                        code="iterate_object_source_not_dict",
                        detail=(
                            f"Rule '{rule_id}': iterate_object source "
                            f"'{source_path}' resolved to {type(source_obj).__name__} "
                            "(expected object)."
                        ),
                        path=source_path,
                        actual=type(source_obj).__name__,
                        expected="object",
                    )
            else:
                missing_keys: list[str] = []
                for entry in obj_spec.get("entries", []):
                    key = entry["key"]
                    if key in source_obj:
                        item = {
                            "key": key,
                            "label": entry.get("label", key),
                            "value": source_obj[key],
                        }
                        event = self._build_event(
                            rule, record, metadata, group_id, ingested_at, parent_id, item,
                            record_index=record_index,
                        )
                        events.append(event)
                    else:
                        missing_keys.append(key)
                if not events and missing_keys and collector is not None:
                    collector.record_skip(
                        code="iterate_object_keys_missing",
                        detail=(
                            f"Rule '{rule_id}': none of the configured "
                            f"iterate_object entry keys ({missing_keys}) were "
                            f"present under '{source_path}'."
                        ),
                        path=source_path,
                        expected=missing_keys,
                        actual=list(source_obj.keys()),
                    )
        else:
            event = self._build_event(
                rule, record, metadata, group_id, ingested_at, parent_id, None,
                record_index=record_index,
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
        *,
        record_index: int = 0,
    ) -> CanonicalEvent:
        ri = record_index

        subject_spec = self._defaults.get("subject_id", {})
        subject_id = _resolve_value(subject_spec, record, item, record_index=ri) or ""

        ts_spec = rule.get("timestamp", {})
        timestamp = _resolve_value(ts_spec.get("start"), record, item, record_index=ri) or ""
        timestamp_end = _resolve_value(ts_spec.get("end"), record, item, record_index=ri)
        duration = _resolve_value(ts_spec.get("duration_seconds"), record, item, record_index=ri)

        p_spec = rule.get("payload", {})
        value = _resolve_value(p_spec.get("value"), record, item, record_index=ri)
        raw_value = _resolve_value(p_spec.get("raw_value"), record, item, record_index=ri)
        unit = _resolve_value(p_spec.get("unit"), record, item, record_index=ri)
        label = _resolve_value(p_spec.get("label"), record, item, record_index=ri)

        components = None
        if "components" in p_spec:
            components = []
            for c_spec in p_spec["components"]:
                c_val = _resolve_value(c_spec.get("value"), record, item, record_index=ri)
                c_unit = _resolve_value(c_spec.get("unit"), record, item, record_index=ri) if "unit" in c_spec else None
                components.append(Component(
                    name=c_spec["name"],
                    value=c_val,
                    unit=c_unit,
                ))

        ctx_defaults = self._defaults.get("context", {})
        ctx_source = _resolve_value(ctx_defaults.get("source"), record, item, record_index=ri) or self._match["source"]
        ctx_modality_str = _resolve_value(ctx_defaults.get("modality"), record, item, record_index=ri) or "unknown"
        ctx_device = _resolve_value(ctx_defaults.get("device"), record, item, record_index=ri) or metadata.device
        ctx_smt = _resolve_value(ctx_defaults.get("source_measurement_type"), record, item, record_index=ri)

        try:
            ctx_modality = Modality(ctx_modality_str)
        except ValueError:
            ctx_modality = Modality.UNKNOWN

        extensions = None
        ext_spec = rule.get("extensions")
        if ext_spec:
            extensions = {}
            for key, val_spec in ext_spec.items():
                extensions[key] = _resolve_value(val_spec, record, item, record_index=ri)

        quality_overrides = rule.get("quality_overrides")
        if quality_overrides:
            if extensions is None:
                extensions = {}
            extensions["_quality_override"] = quality_overrides

        quality_flags: list[QualityFlag] = []
        q_spec = rule.get("quality", {})
        for flag_spec in q_spec.get("flags", []):
            if "condition" in flag_spec:
                cond = flag_spec["condition"]
                cond_val = _resolve_value({"path": cond["path"]}, record, item, record_index=ri)
                if cond_val != cond.get("equals"):
                    continue
            f = flag_spec.get("flag", flag_spec)
            quality_flags.append(QualityFlag(
                code=f.get("code", "UNKNOWN"),
                severity=Severity(f.get("severity", "info")),
                stage=f.get("stage", "structured"),
                message=f.get("message"),
            ))

        srid_spec = self._defaults.get("source_record_id")
        if srid_spec is not None:
            source_record_id = str(_resolve_value(srid_spec, record, item, record_index=ri) or "")
        else:
            user_id = _resolve_value({"path": "userId"}, record) or ""
            m_type = _resolve_value({"path": "measurementType"}, record) or ""
            m_dt = _resolve_value({"path": "measurementDateTime"}, record) or ""
            source_record_id = f"{ctx_source}:{user_id}:{m_type}:{m_dt}"

        rule_type = _resolve_value(rule["type"], record, item, record_index=ri)
        rule_category = _resolve_value(rule["category"], record, item, record_index=ri)
        rule_granularity = _resolve_value(
            rule.get("granularity", "unknown"), record, item, record_index=ri
        ) or "unknown"

        return CanonicalEvent(
            event_id=CanonicalEvent.new_id(),
            subject_id=str(subject_id),
            timestamp=str(timestamp) if timestamp else "",
            timestamp_end=str(timestamp_end) if timestamp_end else None,
            duration_seconds=float(duration) if duration is not None else None,
            type=EventType(rule_type),
            category=str(rule_category) if rule_category is not None else "unknown",
            granularity=Granularity(rule_granularity),
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

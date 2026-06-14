# Canonical event

Every stage operates on the same value object: the `CanonicalEvent`
(`backend/domain/models.py`). This is the exact JSON shape returned in the `events` array of an
`/api/transform` response — the output of `CanonicalEvent.to_dict()`.

## JSON shape

```json
{
  "event_id": "uuid",
  "subject_id": "u1",
  "timestamp": "2025-01-12T06:04:00.000Z",
  "timestamp_end": null,
  "duration_seconds": null,
  "type": "measurement",
  "category": "weight",
  "granularity": "instant",
  "payload": {
    "raw_value": 72.5,
    "value": 72.5,
    "unit": "kg",
    "label": "Weight",
    "components": [
      { "name": "systolic", "value": 120, "unit": "mmHg" }
    ]
  },
  "context": {
    "source": "withings",
    "modality": "scale",
    "device": null,
    "source_measurement_type": "Weight"
  },
  "provenance": {
    "source_record_id": "withings:u1:1:2025-01-12T06:04:00Z",
    "ingested_at": "2025-01-12T09:00:00.000Z",
    "group_id": "uuid",
    "parent_event_id": null,
    "adapter": "withings-body-scale-v1",
    "adapter_version": "1.0.0"
  },
  "mapping": {
    "standard_code": null,
    "standard_system": null,
    "standard_display": null,
    "confidence": null,
    "method": null,
    "concept_id": null,
    "standard_concept": null
  },
  "quality": {
    "flags": [
      { "code": "UNIT_INFERRED", "severity": "info", "stage": "cleaned", "message": "..." }
    ],
    "conformance": "ok",
    "completeness": 1.0,
    "plausibility": "ok",
    "expected_field_count": 4,
    "present_field_count": 4
  },
  "stage": "standardized",
  "extensions": { "withings.attrib": 0 }
}
```

## Field reference

### Top level

| Field | Type | Notes |
|---|---|---|
| `event_id` | string (uuid) | unique per event |
| `subject_id` | string | always non-empty (see [subject_id](../dsl/reference.md#subject_id-mandatory)) |
| `timestamp` | string | ISO 8601; the canonical event time |
| `timestamp_end` | string \| null | for interval events |
| `duration_seconds` | float \| null | |
| `type` | enum | `measurement` \| `observation` \| `survey` \| `event` \| `summary` \| `session` |
| `category` | string | canonical category (drives quality rules) |
| `granularity` | enum | `instant` \| `interval` \| `daily` \| `session` \| `unknown` |
| `stage` | enum | the last stage reached; `standardized` in a full response |
| `extensions` | object \| null | public metadata only — internal `_`-prefixed keys are stripped |

### `payload`

| Field | Notes |
|---|---|
| `raw_value` | the original value, **preserved through every stage** |
| `value` | the cleaned/coerced headline value (`int`/`float`/`str`/`bool`/null) |
| `unit` | unit string or null |
| `label` | human-readable label or null |
| `components` | list of `{ name, value, unit }` or null |

### `context`

`source`, `modality` (one of the [modality enum](../dsl/reference.md#context) values), `device`,
`source_measurement_type`.

### `provenance`

`source_record_id`, `ingested_at`, `group_id` (groups events emitted from one record),
`parent_event_id` (set by `parent:`/iteration linking), `adapter`, `adapter_version`.

### `mapping`

Terminology binding produced by the mapper stage: `standard_code`, `standard_system`,
`standard_display`, `confidence`, `method`, plus OMOP `concept_id` and `standard_concept`. All
null until a binding is applied.

### `quality`

| Field | Notes |
|---|---|
| `flags` | append-only list of `{ code, severity, stage, message }` |
| `conformance` | `ok` \| `issues` \| null |
| `completeness` | ratio 0.0–1.0 \| null |
| `plausibility` | `ok` \| `review` \| `exclude` \| null |
| `expected_field_count` / `present_field_count` | audit counts behind the completeness ratio |

## Internal extension keys

Extension keys with a leading underscore are pipeline plumbing and are **stripped** by `to_dict()`
— they never appear in API responses:

- `_quality_override` — per-rule rule overrides from the adapter (consumed by the validator).
- `_concept_codings` — unit / component / category terminology bindings (consumed by the FHIR
  builder).

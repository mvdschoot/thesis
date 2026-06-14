# API contract

The backend is a single FastAPI service. The pipeline is stateless — no persistence between
requests. Schemas live in `backend/api/models.py`; handlers in `backend/api/routes.py`.

## `POST /api/transform`

Run data + a config through the whole pipeline.

### Request — `TransformRequest`

```json
{
  "data": [ /* JSON array/object, or a CSV string when format=csv */ ],
  "yaml": "<the YAML config>",
  "source": "withings",
  "device": "Withings Body+",
  "format": "json",
  "concept_mappings": { "<slot key>": { "system": "...", "code": "...", "display": "..." } },
  "concept_scan_only": false
}
```

| Field | Required | Notes |
|---|---|---|
| `data` | yes | JSON value, or a CSV string when `format: "csv"` |
| `yaml` | yes | the adapter config |
| `source` | no | must equal the config's `match.source` |
| `device` | no | becomes `context.device` default |
| `format` | no | `json` (default) or `csv` |
| `concept_mappings` | no | user-picked codings keyed by slot (see [mapper](stages.md#5-mapper)) |
| `concept_scan_only` | no | if true, run only connector → adapter → slot detection (skip clean/validate/qualify/FHIR/OMOP) |

### Response — `TransformResponse`

```json
{
  "events": [ /* CanonicalEvent.to_dict() objects */ ],
  "stats": { /* merged stats from qualifier, mapper, fhir, omop */ },
  "bundle": { /* FHIR R4 Bundle, or null if fhir disabled */ },
  "omop_cdm": { /* OMOP CDM tables, or null if omop disabled */ },
  "concept_slots": [ /* ConceptSlot objects for the binding UI */ ],
  "adapter_diagnostics": { /* per-rule emit/skip diagnostics */ }
}
```

The `events` objects are exactly the [canonical event](canonical-event.md) shape. The
`adapter_diagnostics` object is documented under [Diagnostics](../dsl/diagnostics.md).

## Other endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/generate-config` | LLM-generate a config from a data sample + description |
| `POST /api/suggest-config-fix` | LLM-repair a config that emitted 0 events (takes YAML + diagnostics + a sample record) |
| `POST /api/edit-config` | LLM apply a natural-language edit to a working config |
| `POST /api/suggest-concepts` | LLM + OMOPHub tool-calling to suggest terminology codes for concept slots |
| `GET /api/terminology/search` | OMOPHub semantic search proxy (LOINC, SNOMED, UCUM, …) |
| `GET /api/configs`, `GET/PUT /api/configs/{id}` | saved-config CRUD |
| `POST /api/configs/match` | test which saved configs match a data sample |
| `GET /api/healthz` | health check |

## Notes

- **Anti-hallucination guard.** `/api/suggest-concepts` validates that every code the LLM returns
  was actually seen in an OMOPHub tool response — fabricated codes are rejected.
- **The config corpus is the few-shot set.** `backend/configs/examples/` doubles as the few-shot
  prompt for `/api/generate-config`; adding clean canonical examples there improves generation.

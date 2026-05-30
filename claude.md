# CLAUDE.md

This file orients future Claude Code sessions in this repository. The README.md is the user-facing primer; this file captures design intent, invariants, and gotchas that aren't obvious from reading the code.

## Purpose

A thesis-grade ETL web app that turns heterogeneous health/behavioural data (Fitbit, Withings, app-usage logs, linguistic games, virtual supermarket, clinical pilot CSVs, questionnaires) into a single canonical event model, FHIR R4 Bundles, and OMOP CDM v5.4 tables via LLM-generated YAML adapter configs. The thesis claim is **progressive harmonization**: every record advances through explicit stages (`raw → structured → cleaned → validated → qualified → mapped → standardized`), each stage leaving an audit trail of `QualityFlag` entries. The pipeline is stateless per HTTP request — no persistence between calls.

## Architecture at a glance

Single FastAPI process. Three flat tiers — `api/` (HTTP), `pipeline/` (seven harmonization stages, in-process), `domain/` (value objects). No Kafka, no worker glue, no message broker. F5 the launch config and breakpoints in any stage fire on the next request.

```
impl/
  backend/        FastAPI single-service ETL (Python ≥ 3.11)
    api/          HTTP layer
      main.py     FastAPI app + CORS
      routes.py   handlers; /api/transform calls run_pipeline directly
      models.py   Pydantic request/response schemas
      configs_store.py    YAML config CRUD on backend/configs/existing_configs/
      prompts.py          LLM system + user prompt builders
      terminology.py      OMOPHub semantic search client (LOINC, SNOMED, UCUM, …)
      llm/                LLMClient protocol + LangChain backend + tool definitions
    pipeline/     stage implementations
      __init__.py         run_pipeline(...) orchestrator
      connector/          raw input → list[record]; exposes run()
      adapter/            ConfigAdapter + diagnostics; exposes run()
      cleaner/            heuristic chain; exposes run()
      validator/          validation runner; exposes run()
      qualifier/          cross-event quality + stats; exposes run()
      mapper/             concept-slot detection + terminology binding; exposes run()
      fhir/               FHIR R4 Bundle builder; exposes run()
      omop/               OMOP CDM v5.4 table builder; exposes run()
    domain/       value objects (no I/O)
      models.py           CanonicalEvent, Payload, Quality, Stage, …
      rules.py            quality_rules.yaml loader
      coerce.py           try_coerce_numeric (used by cleaner + adapter)
    configs/
      quality_rules.yaml  canonical category quality rules
      examples/           few-shot YAMLs for /api/generate-config
      existing_configs/   user-saved + LLM-generated adapter configs
    pyproject.toml
    Dockerfile
  frontend/       Next.js (app router, output: export) + Monaco editor
    app/          single-page route
    components/   ConnectorPanel, AdapterPanel, ResultsPanel (events, FHIR, OMOP, concepts, debug), navigation
  sample_data/    fixtures (mHealth, Fitabase CSVs, clinical pilots, serious games, VR, questionnaires)
  docker-compose.yml      services: `api`, `frontend`, `hapi-fhir`, `hapi-db`
```

Pipeline flow (one HTTP request through `/api/transform`):

```
data, yaml_text, source, format, concept_mappings?
   ↓ pipeline.connector.run        → SourceMetadata, list[record]
   ↓ pipeline.adapter.run          → CanonicalEvent[stage=STRUCTURED] + AdapterDiagnostics
   ↓ pipeline.cleaner.run          → stage=CLEANED   (whitespace strip, timestamp norm, type coerce, unit infer)
   ↓ pipeline.validator.run        → stage=VALIDATED  (required fields, timestamp, payload, unit, range)
   ↓ pipeline.qualifier.run        → stage=QUALIFIED  (completeness, duplicates, Hampel outliers, conformance, plausibility) + stats
   ↓ pipeline.mapper.run           → stage=MAPPED     (concept-slot detection, user-supplied terminology bindings)
   ↓ pipeline.fhir.run             → stage=STANDARDIZED (FHIR R4 Bundle: Patient, Observation, QuestionnaireResponse, Device, Provenance)
   ↓ pipeline.omop.run             → OMOP CDM v5.4 tables (person, measurement, observation, device_exposure, observation_period)
HTTP response (events + stats + bundle? + omop_cdm? + concept_slots + adapter_diagnostics)
```

Each `pipeline.<stage>.run` is a plain Python function — set a breakpoint, hit the endpoint, the breakpoint fires.

## Key abstractions

| Concept | Location | Notes |
|---|---|---|
| `CanonicalEvent` | `backend/domain/models.py` | Dataclass. Composes `Payload`, `Context`, `Provenance`, `Mapping`, `Quality`, `Stage`. |
| `Quality` | same | Holds `flags`, `conformance` (`"ok"`\|`"issues"`), `completeness` (ratio), `plausibility` (`"ok"`\|`"review"`\|`"exclude"`), and audit fields `expected_field_count` / `present_field_count`. Aligns with Kahn et al. 2016 (Conformance / Completeness / Plausibility). |
| `ConfigAdapter` | `backend/pipeline/adapter/config_adapter.py` | Tier-1 YAML-driven adapter — no source-specific Python. Supports dot-paths with `[idx]`, `@item` for iteration, transforms (`start_of_day`, `iso_millis`, …), templates, lookups, conditional quality flags. Exposes `clean_block`, `validate_block`, `qualify_block`, `fhir_block`, `omop_block` parsed from the YAML config. |
| `AdapterDiagnostics` | `backend/pipeline/adapter/diagnostics.py` | Tracks per-rule emit/skip counts and failure reasons. Surfaced in the API response so the frontend can show why records were skipped. |
| `Cleaner` | `backend/pipeline/cleaner/cleaner.py` | Default chain: `WhitespaceStripper → TimestampNormalizer → TypeCoercer → UnitInferrer`. Each is a `BaseHeuristic` (Event→Event, may mutate). |
| `BaseValidator` | `backend/pipeline/validator/base.py` | Validators ASSERT only — must not mutate. Returns `list[QualityFlag]`. The runner appends and de-dups. |
| `ValidationRunner` | `backend/pipeline/validator/runner.py` | Loads `quality_rules.yaml`, runs five built-in validators, sets `stage=VALIDATED`. |
| `Qualifier` | `backend/pipeline/qualifier/qualifier.py` | Cross-event: completeness ratio, duplicate fingerprint, Hampel outlier (median ± 3.5·MAD per `(subject_id, category)`, min group size 5), then derives conformance + plausibility. Sets `stage=QUALIFIED`. |
| `Mapper` | `backend/pipeline/mapper/__init__.py` | Detects concept slots (code, unit, component, category) across qualified events and applies user-supplied `concept_mappings` to populate `event.mapping`. Sets `stage=MAPPED`. Returns slot metadata for the frontend's concept-binding UI. |
| FHIR Builder | `backend/pipeline/fhir/` | Builds FHIR R4 Bundle (Patient, Observation, QuestionnaireResponse, Device, Provenance) from mapped events. Configurable via the `fhir:` YAML block. Sets `stage=STANDARDIZED`. Survey events → `QuestionnaireResponse`; all others → `Observation`. |
| OMOP Builder | `backend/pipeline/omop/` | Projects events into OMOP CDM v5.4 tables (person, measurement, observation, device_exposure, observation_period). Domain routing via OMOPHub FHIR Resolver API. Configurable via the `omop:` YAML block. |
| `OmopHubClient` | `backend/api/terminology.py` | Semantic search client for OMOPHub (OHDSI/ATHENA vocabularies). Supports single and bulk search, maps `vocabulary_id` → FHIR system URI. Used by `/api/terminology/search` and `/api/suggest-concepts`. |
| `quality_rules.yaml` | `backend/configs/quality_rules.yaml` | Central category rules: `expected_fields`, `unit_whitelist`, `range`, `plausibility_thresholds`, `timestamp_window`. Adapter YAMLs may declare per-emit-rule `quality_overrides:` to narrow these. |

## Running the project

Backend (Python ≥ 3.11):

```bash
cd backend
pip install -e .
# create .env with ANTHROPIC_API_KEY (or OPENAI_/GOOGLE_) + LLM_PROVIDER + LLM_MODEL
uvicorn api.main:app --reload --port 8000
```

Or in a container: `docker compose up -d` brings up four services — the FastAPI `api` (:8000), the Next.js `frontend` (:3000), a persistent HAPI FHIR R4 server `hapi-fhir` (:8080, Postgres-backed via `hapi-db` + the `hapi-pgdata` volume). The frontend talks to HAPI **directly** from the browser (export bundles + a "FHIR Server" dashboard) — the backend is not involved in any FHIR-server traffic. The HAPI base URL is baked into the frontend at build time via `NEXT_PUBLIC_FHIR_BASE_URL` (default `http://localhost:8080/fhir`).

For debugging in VS Code, F5 launches the "Debug API" config (defined in `.vscode/launch.json`) — same uvicorn invocation under debugpy. Set a breakpoint anywhere in `pipeline/` and it will hit on the next `/api/transform`.

Frontend (Node ≥ 18):

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

Endpoints (see `backend/api/routes.py`):
- `POST /api/generate-config`, `POST /api/transform`, `POST /api/suggest-config-fix`
- `POST /api/suggest-concepts` (LLM + OMOPHub tool-calling for terminology mapping)
- `GET /api/terminology/search` (OMOPHub semantic search proxy)
- `GET /api/configs`, `GET /api/configs/{id}`, `PUT /api/configs/{id}`, `POST /api/configs/match`
- `GET /api/healthz`

Env vars are documented in README.md (note: `OMOPHUB_API_KEY` is required for terminology features).

## Conventions and invariants

- **Tag, don't drop.** Validation never filters events. Failed-validation events stay in the output with severity-ERROR flags; the qualifier marks them `quality.plausibility="exclude"` so consumers choose their own filter point. This preserves the chain of custody — important for the thesis story.
- **Trail of evidence.** `payload.raw_value` is preserved through every stage. `quality.flags` is append-only; never remove a flag.
- **Internal extension keys** with a leading underscore (e.g. `_quality_override`) are pipeline plumbing. `CanonicalEvent.to_dict()` strips them. Don't surface them in API responses or frontend.
- **Stateless API.** No DB, no shared state between requests. The qualifier's outlier detection therefore only sees the events in the current request — a known limitation, not a bug.
- **Hampel min-group-size = 5.** Below that, Hampel emits `OUTLIER_INSUFFICIENT_DATA` (info) and skips. Don't lower the threshold without statistical justification — MAD collapses to 0 on tiny groups and flags everything.
- **Configs are LLM-generated YAML.** `backend/configs/*.yaml` doubles as the few-shot corpus for `POST /api/generate-config`. New canonical examples there improve prompt quality. The YAML DSL now includes optional `fhir:` and `omop:` blocks that configure the output stages.
- **Adapters declare quality flags too.** `ConfigAdapter` honours per-rule `quality:` blocks (conditional flags). The validator de-dupes against adapter-declared flags by `(code, stage, message)`.
- **Terminology via OMOPHub.** All terminology search (LOINC, SNOMED, UCUM, etc.) goes through the OMOPHub semantic search API (`backend/api/terminology.py`). The LLM concept-suggestion flow (`/api/suggest-concepts`) uses tool-calling to search OMOPHub and validates that every returned code was actually seen in a tool response (anti-hallucination guard).
- **FHIR and OMOP are parallel output projections.** Both run after the mapper stage and operate on the same mapped events. The FHIR builder stamps `Stage.STANDARDIZED` on events; the OMOP builder does not further mutate events. Both are optional and configurable via YAML blocks.

## Where things live

| What | Where |
|---|---|
| FastAPI app | `backend/api/main.py` |
| HTTP routes | `backend/api/routes.py` |
| Pydantic schemas | `backend/api/models.py` |
| LLM client + prompts | `backend/api/llm/`, `backend/api/prompts.py` |
| LLM tool definitions | `backend/api/llm/tools.py` |
| Terminology search client | `backend/api/terminology.py` (OMOPHub) |
| Config CRUD | `backend/api/configs_store.py` |
| Pipeline orchestrator | `backend/pipeline/__init__.py` |
| Connector | `backend/pipeline/connector/` |
| Adapter engine + diagnostics | `backend/pipeline/adapter/` |
| Cleaning heuristics | `backend/pipeline/cleaner/` |
| Validators | `backend/pipeline/validator/` |
| Qualifier | `backend/pipeline/qualifier/` |
| Mapper (concept slots) | `backend/pipeline/mapper/` |
| FHIR R4 builder | `backend/pipeline/fhir/` |
| OMOP CDM v5.4 builder | `backend/pipeline/omop/` |
| Canonical event model | `backend/domain/models.py` |
| Quality rules loader | `backend/domain/rules.py` |
| Quality rules data | `backend/configs/quality_rules.yaml` |
| Adapter examples (= LLM few-shot) | `backend/configs/examples/` |
| User/LLM-saved configs | `backend/configs/existing_configs/` |
| Single-page UI | `frontend/app/page.tsx` + `frontend/components/` |

## Future work / known gaps

- No persistence layer. If added, the qualifier can use cross-request baselines for outlier detection (currently single-request only).
- No formal test suite under `backend/tests/`. Verification has been ad-hoc smoke runs against `sample_data/`.
- `_quality_override` plumbing through `event.extensions` is a deliberate hack to keep the validator stateless. Acceptable; document it if it confuses you again.
- OMOP concept resolution depends on the external OMOPHub API. When `OMOPHUB_API_KEY` is unset, terminology search and OMOP domain routing are unavailable — the pipeline still runs but OMOP rows get `concept_id=0`.
- FHIR CodeableConcepts are text-only unless the user has bound terminology codes via the mapper. Full automated terminology binding (without user review) is not yet implemented.

## Notes for Claude (working style)

- This is a thesis project for a sole developer — concise, decisive recommendations are wanted. Cite frameworks (Kahn et al. 2016 for data quality, Tanaka et al. 2001 for HR ranges) when relevant.
- Don't break the `to_dict()` JSON shape. The frontend depends on it.
- Don't add features, abstractions, or tests beyond what the task requires (see the root system instructions).
- Prefer extending an existing module over creating a new sibling module unless the conceptual separation justifies it (see how cleaning/validation/qualification are split today).

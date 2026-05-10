# CLAUDE.md

This file orients future Claude Code sessions in this repository. The README.md is the user-facing primer; this file captures design intent, invariants, and gotchas that aren't obvious from reading the code.

## Purpose

A thesis-grade ETL web app that turns heterogeneous health/behavioural data (Fitbit, Withings, app-usage logs, linguistic games, virtual supermarket) into a single canonical event model via LLM-generated YAML adapter configs. The thesis claim is **progressive harmonization**: every record advances through explicit stages (`raw → structured → cleaned → validated → qualified → mapped → standardized`), each stage leaving an audit trail of `QualityFlag` entries. The pipeline is stateless per HTTP request — no persistence between calls.

## Architecture at a glance

Single FastAPI process. Three flat tiers — `api/` (HTTP), `pipeline/` (the five harmonization stages, in-process), `domain/` (value objects). No Kafka, no worker glue, no message broker. F5 the launch config and breakpoints in any stage fire on the next request.

```
impl/
  backend/        FastAPI single-service ETL (Python ≥ 3.11)
    api/          HTTP layer
      main.py     FastAPI app + CORS
      routes.py   handlers; /api/transform calls run_pipeline directly
      models.py   Pydantic request/response schemas
      configs_store.py    YAML config CRUD on backend/configs/existing_configs/
      prompts.py          LLM system + user prompt builders
      llm/                LLMClient protocol + LangChain backend
    pipeline/     stage implementations
      __init__.py         run_pipeline(...) orchestrator
      connector/          raw input → list[record]; exposes run()
      adapter/            ConfigAdapter; exposes run()
      cleaner/            heuristic chain; exposes run()
      validator/          validation runner; exposes run()
      qualifier/          cross-event quality + stats; exposes run()
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
    components/   ConnectorPanel, AdapterPanel, ResultsPanel, …
  sample_data/    fixtures (mHealth, MemoryMR, Linguistic Games, Virtual Supermarket)
  docker-compose.yml      one service: `api`
```

Pipeline flow (one HTTP request through `/api/transform`):

```
data, yaml_text, source, format
   ↓ pipeline.connector.run        → SourceMetadata, list[record]
   ↓ pipeline.adapter.run          → CanonicalEvent[stage=STRUCTURED]
   ↓ pipeline.cleaner.run          → stage=CLEANED   (whitespace strip, timestamp norm, type coerce, unit infer)
   ↓ pipeline.validator.run        → stage=VALIDATED (required fields, timestamp, payload, unit, range)
   ↓ pipeline.qualifier.run        → stage=QUALIFIED (completeness, duplicates, Hampel outliers, conformance, plausibility) + stats
HTTP response (events + stats)
```

Each `pipeline.<stage>.run` is a plain Python function — set a breakpoint, hit the endpoint, the breakpoint fires. `MAPPED` and `STANDARDIZED` are declared in the `Stage` enum but not yet implemented — see "Future work" below.

## Key abstractions

| Concept | Location | Notes |
|---|---|---|
| `CanonicalEvent` | `backend/domain/models.py` | Dataclass. Composes `Payload`, `Context`, `Provenance`, `Mapping`, `Quality`, `Stage`. |
| `Quality` | same | Holds `flags`, `conformance` (`"ok"`\|`"issues"`), `completeness` (ratio), `plausibility` (`"ok"`\|`"review"`\|`"exclude"`), and audit fields `expected_field_count` / `present_field_count`. Aligns with Kahn et al. 2016 (Conformance / Completeness / Plausibility). |
| `ConfigAdapter` | `backend/pipeline/adapter/config_adapter.py` | Tier-1 YAML-driven adapter — no source-specific Python. Supports dot-paths with `[idx]`, `@item` for iteration, transforms (`start_of_day`, `iso_millis`, …), templates, lookups, conditional quality flags. |
| `Cleaner` | `backend/pipeline/cleaner/cleaner.py` | Default chain: `WhitespaceStripper → TimestampNormalizer → TypeCoercer → UnitInferrer`. Each is a `BaseHeuristic` (Event→Event, may mutate). |
| `BaseValidator` | `backend/pipeline/validator/base.py` | Validators ASSERT only — must not mutate. Returns `list[QualityFlag]`. The runner appends and de-dups. |
| `ValidationRunner` | `backend/pipeline/validator/runner.py` | Loads `quality_rules.yaml`, runs five built-in validators, sets `stage=VALIDATED`. |
| `Qualifier` | `backend/pipeline/qualifier/qualifier.py` | Cross-event: completeness ratio, duplicate fingerprint, Hampel outlier (median ± 3.5·MAD per `(subject_id, category)`, min group size 5), then derives conformance + plausibility. Sets `stage=QUALIFIED`. |
| `quality_rules.yaml` | `backend/configs/quality_rules.yaml` | Central category rules: `expected_fields`, `unit_whitelist`, `range`, `plausibility_thresholds`, `timestamp_window`. Adapter YAMLs may declare per-emit-rule `quality_overrides:` to narrow these. |

## Running the project

Backend (Python ≥ 3.11):

```bash
cd backend
pip install -e .
# create .env with ANTHROPIC_API_KEY (or OPENAI_/GOOGLE_) + LLM_PROVIDER + LLM_MODEL
uvicorn api.main:app --reload --port 8000
```

Or in a container: `docker compose up -d` (one service, `harmonia-api`, on :8000).

For debugging in VS Code, F5 launches the "Debug API" config (defined in `.vscode/launch.json`) — same uvicorn invocation under debugpy. Set a breakpoint anywhere in `pipeline/` and it will hit on the next `/api/transform`.

Frontend (Node ≥ 18):

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

Endpoints (see `backend/api/routes.py`): `POST /api/generate-config`, `POST /api/transform`, `GET /api/configs`, `POST /api/configs/match`, `PUT /api/configs/{id}`, `GET /api/healthz`. Env vars are documented in README.md.

## Conventions and invariants

- **Tag, don't drop.** Validation never filters events. Failed-validation events stay in the output with severity-ERROR flags; the qualifier marks them `quality.plausibility="exclude"` so consumers choose their own filter point. This preserves the chain of custody — important for the thesis story.
- **Trail of evidence.** `payload.raw_value` is preserved through every stage. `quality.flags` is append-only; never remove a flag.
- **Internal extension keys** with a leading underscore (e.g. `_quality_override`) are pipeline plumbing. `CanonicalEvent.to_dict()` strips them. Don't surface them in API responses or frontend.
- **Stateless API.** No DB, no shared state between requests. The qualifier's outlier detection therefore only sees the events in the current request — a known limitation, not a bug.
- **Hampel min-group-size = 5.** Below that, Hampel emits `OUTLIER_INSUFFICIENT_DATA` (info) and skips. Don't lower the threshold without statistical justification — MAD collapses to 0 on tiny groups and flags everything.
- **Configs are LLM-generated YAML.** `backend/configs/*.yaml` doubles as the few-shot corpus for `POST /api/generate-config`. New canonical examples there improve prompt quality.
- **Adapters declare quality flags too.** `ConfigAdapter` honours per-rule `quality:` blocks (conditional flags). The validator de-dupes against adapter-declared flags by `(code, stage, message)`.

## Where things live

| What | Where |
|---|---|
| FastAPI app | `backend/api/main.py` |
| HTTP routes | `backend/api/routes.py` |
| Pydantic schemas | `backend/api/models.py` |
| LLM client + prompts | `backend/api/llm/`, `backend/api/prompts.py` |
| Config CRUD | `backend/api/configs_store.py` |
| Pipeline orchestrator | `backend/pipeline/__init__.py` |
| Connector | `backend/pipeline/connector/` |
| Adapter engine | `backend/pipeline/adapter/config_adapter.py` |
| Cleaning heuristics | `backend/pipeline/cleaner/` |
| Validators | `backend/pipeline/validator/` |
| Qualifier | `backend/pipeline/qualifier/` |
| Canonical event model | `backend/domain/models.py` |
| Quality rules loader | `backend/domain/rules.py` |
| Quality rules data | `backend/configs/quality_rules.yaml` |
| Adapter examples (= LLM few-shot) | `backend/configs/examples/` |
| User/LLM-saved configs | `backend/configs/existing_configs/` |
| Single-page UI | `frontend/app/page.tsx` + `frontend/components/` |

## Future work / known gaps

- `Stage.MAPPED` and `Stage.STANDARDIZED` are declared but not implemented. LOINC / SNOMED-CT / UCUM terminology binding is the natural next slice; `Mapping` dataclass on each event is currently populated empty.
- No persistence layer. If added, the qualifier can use cross-request baselines for outlier detection (currently single-request only).
- No formal test suite under `backend/tests/`. Verification has been ad-hoc smoke runs against `sample_data/mHealth/example data/`.
- `_quality_override` plumbing through `event.extensions` is a deliberate hack to keep the validator stateless. Acceptable; document it if it confuses you again.

## Notes for Claude (working style)

- This is a thesis project for a sole developer — concise, decisive recommendations are wanted. Cite frameworks (Kahn et al. 2016 for data quality, Tanaka et al. 2001 for HR ranges) when relevant.
- Don't break the `to_dict()` JSON shape. The frontend depends on it.
- Don't add features, abstractions, or tests beyond what the task requires (see the root system instructions).
- Prefer extending an existing module over creating a new sibling module unless the conceptual separation justifies it (see how cleaning/validation/qualification are split today).

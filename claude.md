# CLAUDE.md

This file orients future Claude Code sessions in this repository. The README.md is the user-facing primer; this file captures design intent, invariants, and gotchas that aren't obvious from reading the code.

## Purpose

A thesis-grade ETL web app that turns heterogeneous health/behavioural data (Fitbit, Withings, app-usage logs, linguistic games, virtual supermarket) into a single canonical event model via LLM-generated YAML adapter configs. The thesis claim is **progressive harmonization**: every record advances through explicit stages (`raw → structured → cleaned → validated → qualified → mapped → standardized`), each stage leaving an audit trail of `QualityFlag` entries. The pipeline is stateless per HTTP request — no persistence between calls.

## Architecture at a glance

```
impl/
  backend/        FastAPI + config-driven adapter engine (Python ≥ 3.11)
    api/          HTTP routes, LLM client, prompt templates
    src/          domain code (see below)
    configs/      YAML adapter configs (also the LLM few-shot corpus)
                  + quality_rules.yaml (canonical category quality rules)
  frontend/       Next.js (app router, output: export) + Monaco editor
    app/          single-page route
    components/   DataInput, YamlEditor, ResultsPanel, ConfigBrowser
  sample_data/    fixtures (mHealth, MemoryMR, Linguistic Games, Virtual Supermarket)
```

Pipeline flow (one HTTP request through `/api/transform`):

```
JSON record
   ↓ JsonConnector
   ↓ AdapterRegistry.get_adapter(metadata, record)
   ↓ ConfigAdapter.transform(record)        → CanonicalEvent[stage=STRUCTURED]
   ↓ Cleaner.apply_all                      → stage=CLEANED   (timestamp norm, unit infer, type coerce, ws strip)
   ↓ ValidationRunner.apply_all             → stage=VALIDATED (required fields, timestamp, payload, unit, range)
   ↓ Qualifier.apply_all                    → stage=QUALIFIED (completeness, duplicates, Hampel outliers, conformance, plausibility)
HTTP response (events + stats)
```

`MAPPED` and `STANDARDIZED` are declared in the `Stage` enum but not yet implemented — see "Future work" below.

## Key abstractions

| Concept | Location | Notes |
|---|---|---|
| `CanonicalEvent` | `backend/src/models/canonical.py` | Dataclass. Composes `Payload`, `Context`, `Provenance`, `Mapping`, `Quality`, `Stage`. |
| `Quality` | same | Holds `flags`, `conformance` (`"ok"`\|`"issues"`), `completeness` (ratio), `plausibility` (`"ok"`\|`"review"`\|`"exclude"`), and audit fields `expected_field_count` / `present_field_count`. Aligns with Kahn et al. 2016 (Conformance / Completeness / Plausibility). |
| `ConfigAdapter` | `backend/src/adapters/config_adapter.py` | Tier-1 YAML-driven adapter — no source-specific Python. Supports dot-paths with `[idx]`, `@item` for iteration, transforms (`start_of_day`, `iso_millis`, …), templates, lookups, conditional quality flags. |
| `Cleaner` | `backend/src/cleaning/cleaner.py` | Default chain: `WhitespaceStripper → TimestampNormalizer → TypeCoercer → UnitInferrer`. Each is a `BaseHeuristic` (Event→Event, may mutate). |
| `BaseValidator` | `backend/src/validation/base.py` | Validators ASSERT only — must not mutate. Returns `list[QualityFlag]`. The runner appends and de-dups. |
| `ValidationRunner` | `backend/src/validation/runner.py` | Loads `quality_rules.yaml`, runs five built-in validators, sets `stage=VALIDATED`. |
| `Qualifier` | `backend/src/qualification/qualifier.py` | Cross-event: completeness ratio, duplicate fingerprint, Hampel outlier (median ± 3.5·MAD per `(subject_id, category)`, min group size 5), then derives conformance + plausibility. Sets `stage=QUALIFIED`. |
| `quality_rules.yaml` | `backend/configs/quality_rules.yaml` | Central category rules: `expected_fields`, `unit_whitelist`, `range`, `plausibility_thresholds`, `timestamp_window`. Adapter YAMLs may declare per-emit-rule `quality_overrides:` to narrow these. |

## Running the project

Backend (Python ≥ 3.11):

```bash
cd backend
pip install -e .
cp .env.example .env   # set ANTHROPIC_API_KEY (or OPENAI_/GOOGLE_)
uvicorn api.main:app --reload --port 8000
```

Frontend (Node ≥ 18):

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

Endpoints (see `backend/api/routes.py`): `POST /api/generate-config`, `POST /api/transform`, `GET /api/configs`, `POST /api/configs/match`, `GET /api/healthz`. Env vars are documented in README.md.

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
| HTTP API | `backend/api/routes.py` |
| LLM client + prompts | `backend/api/llm/`, `backend/api/prompts.py` |
| Pipeline orchestrator | `backend/src/pipeline.py` |
| Adapter engine | `backend/src/adapters/config_adapter.py` |
| Cleaning heuristics | `backend/src/heuristics/{timestamp,units}.py` (existing) + `backend/src/cleaning/` (new) |
| Validators | `backend/src/validation/` |
| Qualifier | `backend/src/qualification/` |
| Quality rules | `backend/configs/quality_rules.yaml` |
| Adapter examples (= LLM few-shot) | `backend/configs/*.yaml` |
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

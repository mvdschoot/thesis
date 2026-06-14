# The seven stages

Each stage is a subpackage under `backend/pipeline/` exposing a single `run(...)` function. This
page documents, per stage: its input, output, the `Stage` enum it stamps, what it does, the
quality flags it can emit, and which YAML block configures it.

The `Stage` enum (`backend/domain/models.py`):
`raw`, `structured`, `cleaned`, `validated`, `qualified`, `mapped`, `standardized`.

---

## 0. Connector

| | |
|---|---|
| **Input** | raw data (JSON array/object, or CSV text) + `format` + optional `source`/`device` |
| **Output** | `(SourceMetadata, list[record])` |
| **Stamps** | — (runs before the canonical-event stages) |
| **Config block** | none |

Parses the raw payload into a list of record dicts. For `format: json`, a list is used as-is and a
single object is wrapped into a one-element list. For `format: csv`, the text is parsed with
`csv.DictReader` (header row → keys). Emits no quality flags.

---

## 1. Adapter

| | |
|---|---|
| **Input** | `list[record]` + `SourceMetadata` + the parsed `ConfigAdapter` |
| **Output** | `CanonicalEvent[]` |
| **Stamps** | `structured` (from `defaults.stage`) |
| **Config block** | the config core — `match`, `defaults`, `emit` |

The only stage driven entirely by your config. For each record it checks `match.record`, then
walks the `emit` rules: applies each rule's `when:` gate, fans out via `iterate:` /
`iterate_object:`, links `parent:` events, and resolves every field's
[value spec](../dsl/value-specs.md) to build canonical events.

It also enforces "a value is never also a component" by stripping redundant components at load
time, and records per-rule emit/skip [diagnostics](../dsl/diagnostics.md). Quality flags here are
the ones **you declared** in the rule's `quality:` block (conditional or unconditional).

---

## 2. Cleaner

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=structured]` |
| **Output** | `CanonicalEvent[stage=cleaned]` |
| **Stamps** | `cleaned` |
| **Config block** | [`clean`](../dsl/reference.md#clean-optional) |

Runs an ordered chain of heuristics, each of which may mutate the event. Default chain:
`whitespace → timestamp_normalizer → type_coercer → unit_inferrer`.

| Heuristic | Does | Flags it can emit |
|---|---|---|
| `whitespace` | strips whitespace on `payload.value` / `raw_value` / `label` strings | — |
| `timestamp_normalizer` | normalizes `timestamp`/`timestamp_end` to ISO 8601 UTC | `TIMEZONE_ASSUMED_UTC`, `DATE_ONLY_TIMESTAMP`, `TIMESTAMP_FORMAT_PARSED` (all info) |
| `type_coercer` | coerces numeric strings on `payload.value` and components | `VALUE_COERCED` (info) |
| `unit_inferrer` | fills `payload.unit` from a `(source, category)` lookup when null | `UNIT_INFERRED` (info) |

---

## 3. Validator

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=cleaned]` |
| **Output** | `CanonicalEvent[stage=validated]` (never dropped) |
| **Stamps** | `validated` |
| **Config block** | [`validate`](../dsl/reference.md#validate-optional) |

Validators **assert only** — they never mutate. The runner loads the global
`quality_rules.yaml`, overlays any `validate.categories` rules, runs the enabled validators in
canonical order, and de-dups flags by `(code, stage, message)`.

| Validator | Checks | Example flag |
|---|---|---|
| `required_fields` | `subject_id`, `timestamp`, `category` (≠ "unknown"), `type` present | `MISSING_REQUIRED_FIELD` (error) |
| `timestamp_window` | timestamp within the global/overridden window; `end ≥ start` | `TIMESTAMP_BEFORE_WINDOW` / `_AFTER_WINDOW` / `TIMESTAMP_END_BEFORE_START` |
| `payload_shape` | payload value present / well-formed as required | `MISSING_PAYLOAD_VALUE`, `PAYLOAD_STRUCTURE_MISMATCH` |
| `unit_whitelist` | `payload.unit` is in the category whitelist | `UNIT_NOT_IN_WHITELIST` (warning) |
| `range` | numeric `payload.value` within `[min, max]` | the `on_violation.code` (e.g. `HR_OUT_OF_RANGE`) |

---

## 4. Qualifier

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=validated]` |
| **Output** | `(CanonicalEvent[stage=qualified], stats)` |
| **Stamps** | `qualified` |
| **Config block** | [`qualify`](../dsl/reference.md#qualify-optional) |

Cross-event checks plus the summary assessment. Five checks (all enabled by default):

| Check | Does | Flags |
|---|---|---|
| `completeness` | sets `quality.completeness` ratio + `expected/present_field_count` from the category's `expected_fields` | — (a metric) |
| `duplicates` | fingerprints events (default `[subject_id, category, timestamp, payload.value]`, numeric values rounded) and flags repeats | `DUPLICATE_EVENT` (warning) |
| `outliers` | Hampel test (median ± `hampel_k`·MAD) per `(subject_id, category)` | `OUTLIER_HAMPEL` (warning); `OUTLIER_INSUFFICIENT_DATA` (info) when group < `min_group_size` |
| `conformance` | sets `quality.conformance` = `issues` if any non-info conformance-type flag exists, else `ok` | — (derived) |
| `plausibility` | sets `quality.plausibility`: any ERROR → `exclude`; WARNING count ≥ `warning_count_for_review` → `review`; else `ok` | — (derived) |

!!! note "Hampel needs ≥ 5 per group"
    Below `min_group_size` (default 5) the MAD collapses toward 0 and would flag everything, so the
    test is skipped and an info flag is recorded instead.

The stats dict returned here (counts, subjects, flag/severity/plausibility/conformance tallies)
becomes part of the API response.

---

## 5. Mapper

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=qualified]` + optional `concept_mappings` |
| **Output** | `(CanonicalEvent[stage=mapped], slot stats)` |
| **Stamps** | `mapped` |
| **Config block** | none (driven by the request's `concept_mappings`) |

Detects **concept slots** — deduplicated groups of events that should share one terminology
binding — and applies any user-supplied bindings. Three slot kinds:

| Slot kind | Represents | Suggested system | Binding target |
|---|---|---|---|
| `code` | `Observation.code` / component codes | LOINC | `event.mapping` |
| `unit` | `valueQuantity.code` (UCUM) | UCUM | `event.extensions._concept_codings.unit` |
| `category` | `Observation.category` | HL7 observation-category | `event.extensions._concept_codings.category` (auto-bound by default) |

Unbound slots are returned to the frontend so the user can pick codes (optionally via the
LLM + OMOPHub `/api/suggest-concepts` flow). Without bindings, the pipeline still runs — codes are
simply absent (FHIR CodeableConcepts stay text-only; OMOP rows get `concept_id=0`).

---

## 6. FHIR builder

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=mapped]` + optional `FhirConfig` |
| **Output** | `(CanonicalEvent[stage=standardized], { fhir: { bundle, ... } })` |
| **Stamps** | `standardized` |
| **Config block** | [`fhir`](../dsl/reference.md#fhir-optional-omit-by-default) |

Builds a FHIR R4 Bundle (Patient, Observation, QuestionnaireResponse, Device, Provenance). See
[FHIR projection](fhir.md) for the full mapping rules.

---

## 7. OMOP builder

| | |
|---|---|
| **Input** | `CanonicalEvent[stage=mapped]` + optional `OmopConfig` |
| **Output** | `(events unchanged, { omop: { tables, ... } })` |
| **Stamps** | — (does not mutate events) |
| **Config block** | [`omop`](../dsl/reference.md#omop-optional-omit-by-default) |

Projects events into OMOP CDM v5.4 tables (person, measurement, observation, device_exposure,
observation_period, plus custom concepts). Domain routing uses the OMOPHub FHIR Resolver. See
[OMOP projection](omop.md).

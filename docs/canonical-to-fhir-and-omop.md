# Transforming the Canonical Model to FHIR R4 and OMOP CDM v5.4

This document describes how Harmonia's internal canonical event model is projected into two widely-adopted health data standards — **HL7 FHIR R4** and **OHDSI OMOP CDM v5.4** — and analyses the theoretical considerations, structural differences, and implementation decisions that shape each transformation.

---

## 1. Background: Why Two Standards?

FHIR and OMOP serve fundamentally different audiences.

**FHIR** (Fast Healthcare Interoperability Resources) is an *exchange* standard. It defines how health data moves between systems — EHRs, patient apps, lab systems — over HTTP APIs. Its unit of exchange is the **Resource** (Patient, Observation, Device, ...), transported inside **Bundles**. FHIR is document-oriented: each resource is self-describing, carries its own references, and can be consumed in isolation.

**OMOP CDM** (Observational Medical Outcomes Partnership Common Data Model) is an *analytics* standard. It defines a relational schema optimised for large-scale observational research. Its unit of storage is a **row** in a clinical table (`measurement`, `observation`, `drug_exposure`, ...). OMOP is warehouse-oriented: every clinical fact is normalised against a shared **vocabulary** of standard concepts, enabling cross-institutional cohort queries without per-site ETL.

For a progressive harmonization pipeline like Harmonia's, supporting both projections means the same canonical event set can be:

1. **Exchanged** — pushed to a FHIR server or ingested by a FHIR-native EHR.
2. **Analysed** — loaded into an OMOP-compliant analytics warehouse for cohort studies.

Neither projection mutates the canonical events. They are read-only parallel outputs produced after the `QUALIFIED` stage.

---

## 2. The Canonical Model

The `CanonicalEvent` dataclass is the internal contract between pipeline stages. Every health record — regardless of source — is normalised into this shape by the adapter stage, then enriched through cleaning, validation, and qualification.

### Key fields relevant to FHIR/OMOP projection

| Canonical field | Purpose | FHIR target | OMOP target |
|---|---|---|---|
| `event_id` | Unique identifier | `Observation.id` | (no direct equivalent; `measurement_id` / `observation_id` are auto-incremented) |
| `subject_id` | Patient/participant | `Patient.identifier` | `person.person_source_value` → `person_id` |
| `timestamp` / `timestamp_end` | When it happened | `Observation.effectiveDateTime` or `.effectivePeriod` | `measurement_date` / `measurement_datetime` |
| `type` (measurement, observation, survey, ...) | What kind of record | Determines resource type (`Observation` vs `QuestionnaireResponse`) | Drives fallback table routing (`measurement` vs `observation`) |
| `category` | Domain bucket (e.g. "heart-rate") | `Observation.category[].text` | `measurement_source_value` |
| `payload.value` / `.unit` | The measured value | `Observation.valueQuantity` | `value_as_number` + `unit_source_value` |
| `payload.components[]` | Multi-axis measurements (e.g. blood pressure) | `Observation.component[]` | One `measurement` row per component |
| `payload.raw_value` | Original untransformed value | Preserved in `note` or provenance | Not projected (OMOP has no raw-value column) |
| `context.source` / `.device` / `.modality` | Where it came from | `Device` resource + `Observation.device` reference | `device_exposure` table |
| `provenance.adapter` / `.adapter_version` | Which config produced it | `Provenance` resource | Not directly projected |
| `mapping.standard_code` / `.standard_system` | Terminology binding (LOINC, SNOMED, ...) | `Observation.code.coding[]` | `measurement_concept_id` (resolved via OMOPHub) |
| `quality.plausibility` | Data quality verdict | `Observation.status` (`final` / `amended` / `entered-in-error`) | Events with `plausibility=exclude` are skipped |
| `quality.flags[]` | Audit trail of quality checks | `Observation.note[]` | Not projected |
| `extensions._concept_codings` | Internal bag for unit/component/category codings | Read by the FHIR builder for `coding[]` arrays | Read by the OMOP builder for unit concept resolution |

---

## 3. The MAPPED Stage: Terminology Binding

Before either projection runs, the **mapper stage** (`pipeline/mapper/`) binds user-selected terminology concepts to canonical events. This is the `QUALIFIED → MAPPED` transition.

### How it works

1. **Slot detection.** The mapper walks all events and groups them into **slots** — sets of events that share the same coding target. Slot types:
   - `code` — the headline measurement (e.g. all "heart-rate" events share one LOINC code)
   - `unit` — the unit of measure (e.g. "bpm" → UCUM code)
   - `component` — sub-measurements within a composite event
   - `category` — the FHIR observation category bucket (vital-signs, activity, exam, survey)

2. **User picks.** The API returns `concept_slots[]` to the frontend. The user searches terminologies via OMOPHub's semantic search and selects a `{system, code, display}` coding for each slot.

3. **Binding.** On the next `/api/transform` call, the mapper applies each pick:
   - **Code** bindings → `event.mapping.standard_code/system/display` (the public `Mapping` dataclass).
   - **Unit / component / category** bindings → `event.extensions["_concept_codings"]` (a private extension bag stripped by `to_dict()`).

4. **Stage advance.** Every event is stamped `stage=MAPPED` regardless of whether any binding was applied. This ensures downstream stages see a uniform state.

### Rationale for the slot model

Wearable and PGHD data is highly repetitive — a Fitbit heart rate dataset may contain 86,400 events per day, all needing the same LOINC code (8867-4, Heart rate). The slot model lets the user pick once and apply to thousands of events, rather than coding individually.

---

## 4. Transformation to FHIR R4

### 4.1 Theoretical grounding

FHIR R4 models clinical facts as **resources** connected by **references**. The relevant resource types for patient-generated health data are:

| FHIR resource | Role |
|---|---|
| **Patient** | The person being measured. In Harmonia, a synthesized stub with `identifier` only (no PII). |
| **Observation** | The primary clinical resource. Covers measurements (heart rate, weight, steps) and general observations. Supports `component[]` for multi-axis data (e.g. blood pressure systolic + diastolic). |
| **Questionnaire** | Survey definition. One per unique survey `category`, listing the questions (`item[]` with `linkId`, `text`, `type`). Linked from `QuestionnaireResponse.questionnaire`. |
| **QuestionnaireResponse** | Survey data. Each `payload.component` becomes an `item[]` with `linkId` and `answer[]`. References a `Questionnaire` via `questionnaire`. |
| **Device** | The measurement device (e.g. "Fitbit Charge 6"). Linked from `Observation.device`. |
| **Provenance** | Audit trail — which adapter, at what time, produced which observations. |

Resources are packaged in a **Bundle**, which can be:
- `transaction` — each entry has a `request` block (`PUT`/`POST`), suitable for uploading to a FHIR server.
- `collection` — entries are informational, no request semantics.

### 4.2 Mapping rules

**Event type → resource type:**

| Canonical `type` | FHIR resource |
|---|---|
| `measurement`, `observation`, `event`, `session`, `summary` | `Observation` |
| `survey` | `QuestionnaireResponse` |

**Quality → status mapping:**

| `quality.plausibility` | `Observation.status` | `QuestionnaireResponse.status` |
|---|---|---|
| `"ok"` or `None` | `final` | `completed` |
| `"review"` | `amended` | `amended` |
| `"exclude"` | `entered-in-error` | `entered-in-error` |

**Timestamps → `effective[x]`:**

- If both `timestamp` and `timestamp_end` are present → `effectivePeriod { start, end }`.
- If only `timestamp` → `effectiveDateTime`.

**Values → `value[x]`:**

| Canonical value type | FHIR slice |
|---|---|
| `int` / `float` | `valueQuantity { value, unit, system (UCUM), code }` |
| `bool` | `valueBoolean` |
| Anything else (string, None) | `valueString` |

**Components:**

Each `payload.components[]` entry becomes an `Observation.component[]` element with its own `code` (CodeableConcept) and `value[x]`.

**Quality flags → notes:**

All `quality.flags[]` entries are serialized as `Observation.note[]` with the format `[severity/code] message`. This preserves the audit trail in the FHIR representation without using extensions.

**Category text bucketing:**

Events are classified into coarse FHIR Observation categories based on `event.type` and `event.category`:

| Condition | Category text |
|---|---|
| `type=survey` | `"survey"` |
| `type=observation` | `"exam"` |
| `type=event` or `type=session` | `"activity"` |
| `category` ∈ {weight, heart-rate, blood-pressure, ...} | `"vital-signs"` |
| `category` ∈ {steps, calories, sleep, ...} | `"activity"` |
| Fallback | `"exam"` |

When the mapper stage has bound a standard observation-category code (from `http://terminology.hl7.org/CodeSystem/observation-category`), the category CodeableConcept carries both `text` and `coding[]`. Otherwise it carries `text` only — FHIR R4 permits text-only CodeableConcepts.

### 4.3 Reference integrity

All intra-bundle references use **UUID5** identifiers derived from deterministic seeds:

- `subject_uuid(subject_id)` — Patient
- `device_uuid(source, device)` — Device
- `observation_uuid(event_id)` — Observation / QuestionnaireResponse
- `questionnaire_uuid(category)` — Questionnaire (one per survey category)
- `provenance_uuid(adapter_id|version|timestamp)` — Provenance

This guarantees:
1. Identical inputs produce identical UUIDs across runs (idempotent `PUT`).
2. Every `urn:uuid:` reference in the bundle resolves to a `fullUrl` in the same bundle.
3. A post-build verification pass (`_verify_references`) walks the bundle and reports dangling references.

### 4.4 Implementation

The FHIR stage lives in `pipeline/fhir/`:

```
pipeline/fhir/
  __init__.py   → run(events, config) → (events, stats)
  config.py     → FhirConfig: enabled, bundle_type, include
  builder.py    → build_bundle(): resource construction logic
  refs.py       → UUID5 minting for stable references
```

Enabled/disabled via the `fhir:` block in the YAML adapter config:

```yaml
fhir:
  enabled: true
  bundle_type: transaction          # or "collection"
  include: [Patient, Observation, Questionnaire]  # subset of [Patient, Observation, Device, Provenance, Questionnaire]
```

When `Questionnaire` is in the `include` list, the builder collects all survey events, groups them by category, and emits one `Questionnaire` definition per unique category. Each `QuestionnaireResponse` is linked to its definition via the `questionnaire` field. The Questionnaire's `item[]` is inferred from the `payload.components[]` of the first event with that category — each component name becomes a `linkId`, and the item type is inferred from the value (`integer`, `decimal`, `boolean`, or `string`).

When enabled, `run()` builds the bundle, stamps `stage=STANDARDIZED` on every event, and returns stats including the serialized bundle, resource count, byte size, and any dangling references.

---

## 5. Transformation to OMOP CDM v5.4

### 5.1 Theoretical grounding

The OMOP CDM is a **person-centric relational schema** designed for observational research. Each clinical fact occupies one row in a domain-specific table, identified by a **concept_id** from the OHDSI Standardized Vocabularies.

The tables relevant for patient-generated health data:

| OMOP table | Content | Key columns |
|---|---|---|
| **person** | One row per unique participant | `person_id`, `person_source_value` |
| **measurement** | Quantitative clinical results (heart rate, weight, lab values) | `measurement_concept_id`, `value_as_number`, `unit_concept_id` |
| **observation** | Qualitative or non-quantitative facts (survey answers, textual observations) | `observation_concept_id`, `value_as_string`, `value_as_number` |
| **device_exposure** | Periods during which a device was used | `device_concept_id`, `device_exposure_start/end_date` |
| **observation_period** | The time span during which a person's data is available | `observation_period_start/end_date` |

### 5.2 Concept resolution: the central challenge

The defining characteristic of OMOP is that every clinical fact must carry a **standard concept_id** from the OHDSI vocabulary. This is fundamentally different from FHIR, where text-only CodeableConcepts are valid.

Harmonia resolves concepts through **OMOPHub** (`api.omophub.com`), a hosted OHDSI/ATHENA vocabulary service:

1. **Collect FHIR codings.** The builder walks all MAPPED events and collects unique `(system, code)` pairs from `event.mapping` and `event.extensions._concept_codings`.

2. **Batch resolve.** Sends FHIR codings to OMOPHub's `/v1/fhir/resolve/batch` endpoint, which returns:
   - `source_concept` — the concept that directly represents the input code.
   - `standard_concept` — the OHDSI standard concept it maps to (may differ from source).
   - `target_table` — the OMOP domain table the concept belongs to (measurement, observation, ...).
   - `mapping_type` — `"direct"` (code is already standard), `"mapped"` (mapped via relationship), `"semantic_match"` (LLM-based match), or `"unmapped"`.

3. **Fallback.** When the resolver returns no `target_table`, a heuristic determines the table:
   - `type=survey` → `observation`
   - Numeric value → `measurement`
   - Everything else → `observation`

4. **concept_id=0.** Unresolved codings are emitted with `concept_id=0` (OMOP convention: "No matching concept"). The event is **not dropped** — consistent with the pipeline's "tag, don't drop" principle. An audit record is added to the `unmapped[]` list.

### 5.3 Mapping rules

**Subject → person:**

`person_id` is a deterministic 31-bit integer derived from `SHA-256(subject_id)`. This avoids requiring an external person registry while producing stable IDs across runs. `person_source_value` preserves the original `subject_id`.

**Events → measurement / observation:**

| Condition | Target table | Value column |
|---|---|---|
| `target_table="measurement"` from resolver | `measurement` | `value_as_number` (numeric values only) |
| `target_table="observation"` from resolver | `observation` | `value_as_number` or `value_as_string` |
| Fallback: `type=survey` | `observation` | `value_as_string` |
| Fallback: numeric payload | `measurement` | `value_as_number` |
| Fallback: everything else | `observation` | `value_as_string` |

**Components → separate rows:**

Unlike FHIR, OMOP has no `component` construct. Each `payload.components[]` entry becomes a **separate `measurement` row** with:
- Its own `measurement_concept_id` (resolved from the component's bound coding).
- `measurement_source_value` = `"{category}.{component_name}"` (e.g. "heart-rate-zone.minutes").
- Its own `unit_concept_id` and `unit_source_value`.

This is a significant structural difference from FHIR, where components are nested within a single Observation.

**Type concept ID:**

The `*_type_concept_id` column records *how* the data was captured. These are resolved dynamically via OMOPHub's bulk semantic search endpoint (`POST /v1/search/semantic-bulk`), filtering by `concept_class_id: "Type Concept"`. Hardcoded fallback values are used when OMOPHub is unavailable:

| Canonical modality | Fallback type_concept_id | Meaning |
|---|---|---|
| `wearable`, `sensor`, `app`, `game`, `vr` | 32865 | Patient self-report |
| `scale` | 705183 | Patient self-tested |
| `survey` | 32862 | Patient filled survey |
| `unknown` | 32817 | EHR (default) |

**Quality filtering:**

Events with `quality.plausibility="exclude"` are **skipped entirely** in the OMOP projection. This contrasts with FHIR, where excluded events are emitted with `status=entered-in-error`. The rationale: OMOP is analytics-focused, and including implausible data would contaminate downstream cohort queries. Researchers can still access excluded events via the canonical model or the FHIR bundle.

**Device exposure:**

Unique `(source, device)` pairs produce one `device_exposure` row each. The date range spans the earliest to latest event timestamp for that device. `device_concept_id` is left at 0 (no vocabulary for consumer wearable device models in OHDSI).

**Observation period:**

One row per person, spanning the earliest to latest event date. This table is required by many OMOP analytics tools (e.g. ATLAS) and defines the window of "observable" data.

### 5.4 Implementation

The OMOP stage lives in `pipeline/omop/`:

```
pipeline/omop/
  __init__.py   → run(events, config) → (events, stats)
  config.py     → OmopConfig: enabled, include (list of table names)
  tables.py     → dataclasses: OmopPerson, OmopMeasurement, OmopObservation, OmopDeviceExposure, OmopObservationPeriod
  builder.py    → build_cdm(): concept resolution + row construction
  resolver.py   → batch_resolve(): OMOPHub FHIR Resolver client
```

Enabled/disabled via the `omop:` block in the YAML adapter config:

```yaml
omop:
  enabled: true
  include: [person, measurement, observation, device_exposure, observation_period]
```

The builder returns a dict keyed by table name, each value being a list of row dicts. Resolution statistics (total codings, resolved count, mapping types) are included for transparency.

---

## 6. Key Differences Between the FHIR and OMOP Projections

| Aspect | FHIR R4 | OMOP CDM v5.4 |
|---|---|---|
| **Purpose** | Interoperability / exchange | Observational research / analytics |
| **Data model** | Document-oriented (self-describing resources) | Relational (normalised tables + vocabulary) |
| **Identity** | UUID-based resource IDs with `urn:uuid:` references | Integer IDs (`person_id`, `measurement_id`, ...) |
| **Terminology** | CodeableConcept with `text` + optional `coding[]` | Mandatory `concept_id` from OHDSI vocabulary (0 = unmapped) |
| **Components** | Nested within `Observation.component[]` | Flattened to separate `measurement` rows |
| **Surveys** | `Questionnaire` (definition) + `QuestionnaireResponse` (answers) with `item[]` / `answer[]` | Rows in the `observation` table |
| **Excluded events** | Emitted with `status=entered-in-error` | Skipped entirely |
| **Quality flags** | Preserved as `Observation.note[]` | Not projected |
| **Device info** | `Device` resource with reference from Observation | `device_exposure` table (separate from clinical tables) |
| **Provenance** | `Provenance` resource pointing at all observations | Not projected (no standard provenance table in OMOP CDM) |
| **Observation period** | Not applicable (no bundle-level concept) | `observation_period` table (required by analytics tools) |
| **Output format** | JSON (FHIR Bundle) | Tabular (dict of row lists, ready for SQL INSERT) |
| **Vocabulary service** | N/A (codings come from the mapper stage) | OMOPHub FHIR Resolver (resolves FHIR codings → OMOP concept_ids) |
| **Idempotency** | UUID5-based IDs enable `PUT` upserts | Row IDs are sequential (no built-in upsert semantics) |

---

## 7. Data Flow Summary

```
                 ┌─────────────┐
                 │  Canonical   │
                 │   Events     │
                 │ (QUALIFIED)  │
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │    Mapper    │
                 │  (user picks │
                 │  terminology │
                 │   concepts)  │
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │   Events     │
                 │  (MAPPED)    │
                 │  + codings   │
                 └──────┬───────┘
                        │
            ┌───────────┼───────────┐
            │                       │
     ┌──────▼───────┐       ┌──────▼────────┐
     │  FHIR Stage  │       │  OMOP Stage   │
     │              │       │               │
     │  Build R4    │       │ 1. Collect    │
     │  Bundle:     │       │    codings    │
     │  - Patient   │       │ 2. Resolve    │
     │  - Observ.   │       │    via        │
     │  - QuestResp │       │    OMOPHub    │
     │  - Device    │       │ 3. Route to   │
     │  - Provenance│       │    CDM table  │
     │              │       │ 4. Build rows │
     └──────┬───────┘       └──────┬────────┘
            │                       │
     ┌──────▼───────┐       ┌──────▼────────┐
     │  FHIR R4     │       │  OMOP CDM     │
     │  Bundle      │       │  Table Rows   │
     │  (JSON)      │       │  (dict/JSON)  │
     └──────────────┘       └───────────────┘
```

Both projections are returned in the `/api/transform` response:
- `response.bundle` — the FHIR Bundle (or `null` when disabled)
- `response.omop_cdm` — the OMOP table rows + resolution stats (or `null` when disabled)

---

## 8. Considerations and Design Decisions

### 8.1 Tag, don't drop

The pipeline never silently removes data. In FHIR, excluded events appear with `status=entered-in-error`. In OMOP, excluded events are the only exception — they are skipped because OMOP is designed for analytics, and including implausible data would contaminate query results. However, the OMOP `unmapped[]` list still records events that couldn't be mapped, preserving audit transparency.

### 8.2 Concept resolution is the bottleneck

FHIR is tolerant of missing codings — `text`-only CodeableConcepts are valid. OMOP requires a `concept_id` for every row. This means OMOP is inherently more dependent on vocabulary coverage. Consumer health devices, games, and novel sensors often produce data types with no LOINC or SNOMED equivalent, leading to `concept_id=0` ("No matching concept"). These events are still emitted — they just can't participate in standardised cross-site queries until the vocabulary catches up.

### 8.3 Components: nesting vs. flattening

FHIR's `Observation.component[]` is a natural fit for multi-axis measurements (e.g. blood pressure with systolic and diastolic components). OMOP has no equivalent — each component must become its own row. This means:
- A blood pressure event produces 1 FHIR Observation (with 2 components) but 3 OMOP measurement rows (parent + 2 components).
- The OMOP source value uses dot notation (`"blood-pressure.systolic"`) to preserve the relationship.

### 8.4 Surveys: different resource models

FHIR has a dedicated `QuestionnaireResponse` resource with structured `item[]/answer[]` semantics. OMOP has no survey-specific table — survey responses go into `observation` with `value_as_string` or `value_as_number`. This means survey structure (question linkage, answer ordering) is preserved in FHIR but flattened in OMOP.

### 8.5 Provenance

FHIR supports provenance natively via the `Provenance` resource, which can reference every observation in the bundle and record which adapter produced them. OMOP CDM v5.4 has no standard provenance table, so adapter lineage is not carried into the OMOP projection. The `measurement_source_value` / `observation_source_value` columns partially compensate by recording the canonical category, but they lack the granularity of a full provenance chain.

### 8.6 Stateless projection

Both projections are computed fresh on every `/api/transform` request. There is no persistence layer and no cross-request state. This means:
- OMOP `person_id` values are deterministic (SHA-256 hash) so the same subject always gets the same ID, even across requests.
- OMOP row IDs (`measurement_id`, etc.) are sequential within a single request but not globally unique. A real OMOP warehouse would assign its own IDs on INSERT.
- FHIR UUIDs are deterministic (UUID5) for the same reason — enabling idempotent `PUT` upserts if the bundle is submitted to a FHIR server.

### 8.7 Future: full OMOP vocabulary coverage

The current implementation resolves FHIR codings to OMOP concepts via OMOPHub's FHIR Resolver API. This covers the major vocabulary systems (LOINC, SNOMED-CT, UCUM, RxNorm, ICD-10, CPT). Consumer health metrics that fall outside these vocabularies (e.g. Fitbit's "Active Zone Minutes", game scores, app-specific metrics) remain at `concept_id=0`. A future extension could introduce custom concept mappings or a local vocabulary for PGHD-specific concepts.

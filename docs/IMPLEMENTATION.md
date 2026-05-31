# Harmonia — Implementation Reference (for the thesis write-up)

> **What this document is.** A single, self-contained, exhaustive description of the
> proof-of-concept implementation that accompanies this thesis. It is written for a
> *separate* assistant that will author the implementation chapter(s) and does **not**
> have access to this repository. Everything needed to describe the system accurately
> — the architecture, the canonical data model, the seven-stage pipeline, the YAML
> DSL and the engine that executes it, the FHIR/OMOP projections, the LLM subsystem,
> every HTTP endpoint, the frontend workflow, and the design rationale behind each
> decision — is collected here. Code identifiers, flag codes, constants and thresholds
> are quoted verbatim from the source so they can be cited with confidence.
>
> **Naming note.** The repository/product name used in code and prior docs is
> *Harmonia* (the FastAPI app title is `"Harmonia API"`). The thesis concept is
> *progressive harmonization*. The two are used interchangeably below.
>
> **One honesty caveat.** A handful of exact numbers in `quality_rules.yaml` are quoted
> from a direct read of that file (Section 11). Should the writer wish to quote a
> category not shown here verbatim, it is worth re-checking `backend/configs/quality_rules.yaml`.

---

## 1. Purpose and the thesis claim

Harmonia is a **thesis-grade ETL web application** that turns heterogeneous health
and behavioural data — Fitbit/Fitabase exports, Withings scale data, mobile-app
usage logs, serious-game telemetry, virtual-supermarket/VR sessions, clinical pilot
CSVs and questionnaires — into a **single canonical event model**, and from there
into two widely-adopted health-data standards: **HL7 FHIR R4 Bundles** and **OHDSI
OMOP CDM v5.4 tables**. The transformation rules are not hand-written per source;
they are expressed as **LLM-generated YAML adapter configs** that drive a generic
engine.

### The central claim: progressive harmonization

Every record advances through a sequence of **explicit, named stages**, and each
stage leaves an **audit trail** of `QualityFlag` entries rather than silently
mutating or discarding data. The stages, in order, are:

```
raw → structured → cleaned → validated → qualified → mapped → standardized
```

The thesis argument is that harmonization should be *progressive and observable*:
instead of a black-box "source → FHIR" mapping, each record carries, at every step,
(a) its current canonical form, (b) the original raw value (`payload.raw_value` is
preserved through every stage), and (c) an append-only list of quality flags
explaining what was checked, inferred, normalized, or found suspect.

### Cross-cutting invariants

These invariants are load-bearing for the thesis story and are enforced
throughout the code:

- **Tag, don't drop.** No stage ever filters events out. A record that fails
  validation stays in the output carrying severity-`ERROR` flags; the qualifier
  marks it `quality.plausibility = "exclude"` so that *downstream consumers*
  choose their own filter point. (The only place an event is omitted is the OMOP
  projection, deliberately — see §14.)
- **Trail of evidence.** `payload.raw_value` survives every stage. `quality.flags`
  is append-only — a flag is never removed.
- **Stateless per request.** There is no database and no shared state between HTTP
  requests. The whole pipeline runs in-process for a single request. (Consequence:
  the qualifier's cross-event outlier detection only sees the events in the current
  request — a documented limitation, not a bug.)
- **Determinism.** Identical inputs produce identical outputs across runs: FHIR
  resource IDs are UUID5-derived from stable seeds; OMOP `person_id` is a
  SHA-256-derived integer; custom OMOP concept IDs are hash-derived. This makes the
  FHIR bundle idempotent under `PUT` and the OMOP rows reproducible.
- **Internal extension keys** (leading underscore, e.g. `_quality_override`,
  `_concept_codings`) are pipeline plumbing and are stripped from the public JSON
  by `CanonicalEvent.to_dict()`.

---

## 2. System architecture

Harmonia is a **single FastAPI process** with three flat tiers and no message
broker, no worker glue, no Kafka. The pipeline is just a sequence of ordinary
Python function calls; a developer can set a breakpoint anywhere in `pipeline/`
and it fires on the next HTTP request.

```
impl/
  backend/                 FastAPI single-service ETL (Python ≥ 3.11/3.12)
    api/                   HTTP layer
      main.py              FastAPI app + CORS
      routes.py            request handlers; /api/transform calls run_pipeline directly
      models.py            Pydantic request/response schemas
      configs_store.py     YAML config CRUD on backend/configs/existing_configs/
      prompts.py           LLM system + user prompt builders (the DSL spec lives here)
      terminology.py       OMOPHub semantic-search client (LOINC, SNOMED, UCUM, …)
      llm/                 LLMClient protocol + LangChain backend + tool definitions
    pipeline/              the seven harmonization stages, in-process
      __init__.py          run_pipeline(...) + scan_concepts(...) orchestrators
      connector/           raw input → list[record]            (exposes run())
      adapter/             ConfigAdapter + diagnostics           (exposes run())
      cleaner/             heuristic chain                       (exposes run())
      validator/           validation runner                     (exposes run())
      qualifier/           cross-event quality + stats           (exposes run())
      mapper/              concept-slot detection + binding      (exposes run())
      fhir/                FHIR R4 Bundle builder                (exposes run())
      omop/                OMOP CDM v5.4 table builder           (exposes run())
    domain/                value objects (no I/O)
      models.py            CanonicalEvent, Payload, Quality, Stage, enums …
      rules.py             quality_rules.yaml loader
      coerce.py            try_coerce_numeric (shared by cleaner + adapter)
    configs/
      quality_rules.yaml   canonical per-category quality rules
      examples/            few-shot YAMLs embedded into the generation prompt
      existing_configs/    user-saved + LLM-generated adapter configs (+ descriptors)
  frontend/                Next.js (app router, static export) + Monaco editor
  sample_data/             fixtures (mHealth, Fitabase CSVs, clinical pilots, games, VR, questionnaires)
  docker-compose.yml       services: api, frontend, hapi-fhir, hapi-db
```

### The four deployable services (docker-compose)

1. **`api`** — the FastAPI backend (`:8000`).
2. **`frontend`** — the Next.js single-page app (`:3000`).
3. **`hapi-fhir`** — a persistent HAPI FHIR R4 server (`:8080`), Postgres-backed.
4. **`hapi-db`** — Postgres for HAPI, with a `hapi-pgdata` volume so resources
   survive restarts.

A subtle but important architectural point: **the browser talks to the HAPI FHIR
server directly** (for the "export bundle" action and the "FHIR Server" dashboard).
The backend is *not* involved in any FHIR-server traffic. The HAPI base URL is
baked into the frontend at build time via `NEXT_PUBLIC_FHIR_BASE_URL`
(default `http://localhost:8080/fhir`).

### Request lifecycle (the `/api/transform` path)

```
data, yaml, source?, device?, format?, concept_mappings?
   │
   ▼ connector.run     → SourceMetadata, list[record]
   ▼ adapter.run       → CanonicalEvent[stage=STRUCTURED] + AdapterDiagnostics
   ▼ cleaner.run       → stage=CLEANED      (whitespace, timestamp norm, type coerce, unit infer)
   ▼ validator.run     → stage=VALIDATED    (required fields, timestamp, payload, unit, range)
   ▼ qualifier.run     → stage=QUALIFIED    (completeness, duplicates, Hampel outliers,
   │                                          conformance, plausibility) + stats
   ▼ mapper.run        → stage=MAPPED       (concept-slot detection + user terminology bindings)
   ▼ fhir.run          → stage=STANDARDIZED (FHIR R4 Bundle)
   ▼ omop.run          → OMOP CDM v5.4 tables (does not further mutate events)
HTTP response: events + stats + bundle? + omop_cdm? + concept_slots + adapter_diagnostics
```

---

## 3. The canonical event model

`CanonicalEvent` (in `backend/domain/models.py`) is the **contract between every
pipeline stage**. Every health record, regardless of source, is normalised into
this shape by the adapter stage, then progressively enriched. It is a plain
Python `@dataclass` (no ORM, no I/O).

### Enums

| Enum | Values |
|---|---|
| `EventType` | `measurement`, `observation`, `survey`, `event`, `summary`, `session` |
| `Granularity` | `instant`, `interval`, `daily`, `session`, `unknown` |
| `Modality` | `wearable`, `scale`, `survey`, `sensor`, `app`, `game`, `vr`, `unknown` |
| `Stage` | `raw`, `structured`, `cleaned`, `validated`, `qualified`, `mapped`, `standardized` |
| `Severity` | `info`, `warning`, `error` |
| `MappingMethod` | `rule`, `terminology-lookup`, `ai`, `manual` |
| `StandardSystem` | `LOINC`, `SNOMED-CT`, `UCUM`, `custom` |

### The dataclass and its sub-objects

```python
@dataclass
class CanonicalEvent:
    event_id: str                 # uuid4 minted at construction
    subject_id: str               # the person/participant
    timestamp: str                # ISO 8601, millisecond precision, Z suffix
    type: EventType
    category: str                 # domain bucket, e.g. "heart-rate", "weight"
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
```

- **`Payload`** — `raw_value` (original, preserved forever), `value`
  (`int|float|str|bool|None`), `unit`, `label`, `components: list[Component] | None`.
  A `Component` is `{ name, value, unit? }` — used for multi-axis measurements
  (blood-pressure systolic/diastolic) and for descriptive fields that travel with
  the headline value.
- **`Context`** — `source`, `modality` (a `Modality`), `device`,
  `source_measurement_type`.
- **`Provenance`** — `source_record_id`, `ingested_at`, `group_id` (shared by all
  events emitted from one input record), `parent_event_id` (rule-to-rule linkage),
  `adapter`, `adapter_version`.
- **`Mapping`** — terminology binding: `standard_code`, `standard_system`,
  `standard_display`, `confidence`, `method`, plus OMOP-oriented `concept_id` and
  `standard_concept` (`"S"`/`"C"`/`None`). Populated by the mapper stage.
- **`Quality`** — `flags: list[QualityFlag]`, `conformance` (`"ok"`/`"issues"`),
  `completeness` (ratio 0–1), `plausibility` (`"ok"`/`"review"`/`"exclude"`),
  and the audit counters `expected_field_count` / `present_field_count`. This object
  is deliberately aligned with **Kahn et al. 2016** harmonised data-quality
  terminology (Conformance / Completeness / Plausibility).
- **`QualityFlag`** — `{ code, severity, stage, message }`. The atom of the audit
  trail.

### `to_dict()` and `from_dict()`

`to_dict()` produces the exact JSON shape the frontend depends on. Crucially it
**strips internal extension keys** (any key starting with `_`), so plumbing such as
`_quality_override` and `_concept_codings` never leaks into API responses. If the
resulting public-extensions dict is empty, it is rendered as `null`.

`from_dict()` reconstructs a fully-typed `CanonicalEvent` from that JSON — it exists
so events can be round-tripped without losing dataclass typing.

Two static helpers stamp identity/time: `new_id()` returns a `uuid4` string;
`now_iso()` returns `datetime.utcnow()` to millisecond precision with a `Z` suffix.

---

## 4. Pipeline orchestration

`backend/pipeline/__init__.py` wires the stages together. It exposes two entry
points.

### `run_pipeline(...)`

```python
def run_pipeline(*, data, yaml_text=None, parsed_config=None, source=None,
                 format="json", device=None, concept_mappings=None
                 ) -> tuple[list[CanonicalEvent], dict, AdapterDiagnostics]:
```

It parses the YAML once (or accepts an already-parsed `parsed_config`), constructs
a `ConfigAdapter`, and then calls each stage in order:

```python
config_adapter = ConfigAdapter.from_dict(parsed)
collector = DiagnosticsCollector()
metadata, records = connector.run(data, format=format, source=source, device=device)
structured = adapter.run(records, metadata=metadata, adapter=config_adapter, diagnostics=collector)
adapter_diagnostics = collector.finalize(len(structured))
cleaned    = cleaner.run(structured,  config=config_adapter.clean_block)
validated  = validator.run(cleaned,   config=config_adapter.validate_block)
qualified, stats = qualifier.run(validated, config=config_adapter.qualify_block)
_strip_quality_overrides(qualified)            # remove the _quality_override plumbing
mapped, mapper_stats     = mapper.run(qualified, mappings=concept_mappings)
standardized, fhir_stats = fhir.run(mapped,      config=config_adapter.fhir_block)
_, omop_stats            = omop.run(standardized, config=config_adapter.omop_block)
```

Each `pipeline.<stage>.run` is a plain function, and the per-stage configuration is
forwarded straight from the parsed YAML blocks exposed as
`config_adapter.{clean,validate,qualify,fhir,omop}_block`. The returned `stats`
dict is the union of the qualifier stats and the mapper/FHIR/OMOP stats; the route
handler later flattens parts of it (see §17).

`_strip_quality_overrides` is lifted to the orchestrator (rather than living in the
qualifier) so cleanup still happens even when the qualifier is disabled via
`qualify.enabled`.

### `scan_concepts(...)` — the fast path

```python
def scan_concepts(*, data, yaml_text=None, parsed_config=None, source=None,
                  format="json", device=None
                  ) -> tuple[list[dict], AdapterDiagnostics]:
```

A lightweight discovery path that runs only **connector → adapter →
cleaner → mapper.detect_slots()**, skipping validation, qualification, FHIR and
OMOP. It exists so the frontend can present concept slots for a *small sample*
before committing to a full transform of a large dataset. It is reached via the
`concept_scan_only` flag on `/api/transform`.

---

## 5. The YAML adapter DSL — specification

This is the heart of the contribution: a declarative DSL in which one YAML
document fully specifies how to turn a source's records into canonical events
(and how to configure the downstream stages), **with no source-specific Python**.
The same spec is what the LLM is taught (it is embedded verbatim into the
generation prompt — see §16), so the DSL definition and the LLM's instructions are
one and the same artifact (`DSL_OVERVIEW` in `backend/api/prompts.py`).

### 5.1 Top-level sections

| Section | Required | Purpose |
|---|---|---|
| `adapter` | yes | `{ id, version, description }` — identifies this config. |
| `match` | yes | `{ source, record? }` — which records this config handles. |
| `defaults` | no | `{ subject_id, context, stage, source_record_id }` applied to every event. |
| `emit` | yes | a list of rules; each produces 0..n events per input record. |
| `clean` | no | cleaner chain composition + per-heuristic params. |
| `validate` | no | which validators run + per-category overlay on `quality_rules.yaml`. |
| `qualify` | no | which cross-event checks run + tunables. |
| `fhir` | no | toggles + bundle shape for the FHIR R4 output. |
| `omop` | no | toggles + table selection for the OMOP CDM output. |

**Omission rule:** every block, key and parameter is optional except `adapter`,
`match` and `emit`. Omitted = current default behaviour. The LLM is explicitly
told *not to invent thresholds* — if a parameter cannot be inferred from the
sample, it omits it and the statistically-defensible defaults apply.

### 5.2 The `match` block and "match-block rigidity"

`match.source` must equal the request's source name (string equality).
`match.record` is an optional list of **predicate entries, implicitly AND-ed**.
Each entry has a `field` (a dot-path supporting `[index]`) and one or more verbs
(AND-ed within the entry):

- `equals: X` — exact equality
- `in: [A, B, C]` — membership
- `exists: true | false` — `true`: value is non-null/present; `false`: null/missing
- `type: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null"`
- `non_empty: true` — arrays/strings/objects must have length > 0

A deliberate design rule (taught as **MANDATORY** to the LLM) is that the match
block must be *strict*. It must assert `exists: true` on every field the
`defaults`/`emit` rules read, `type: array, non_empty: true` on every `iterate`
target, `type: object` on intermediate containers, and pin any discriminator field
(e.g. `dataType`, `measurementType`) with `equals`/`in`. The rationale: a match
block that accepts a garbage record is a bug — false positives produce unusable
events, whereas false negatives surface cleanly in the UI as "no config matches",
which the user can then widen. The input data is always *leading*: even if it
deviates from a supplied schema descriptor, the match block must match the data.

### 5.3 Value-spec forms (usable anywhere a value is needed)

This is the expression language. A value spec is either a literal or a one-key
dict:

- **literal:** `"foo"`, `42`, `null`
- **path:** `{ path: "some.nested.key" }` — dot notation, `[0]` indexing.
  Inside an iterated rule, prefix `@item.` to reference the current element and
  `@event.` (or `@event` alone) to reach back up to a field on the whole record.
  `{ path: "@record_index" }` yields the 0-based row number (useful as a synthetic
  `subject_id`).
- **transform:** `{ path: "...", transform: "start_of_day" | "end_of_day" | "iso_date" | "iso_millis" | "to_int" | "to_float" }`
- **fallback:** `{ path: "...", fallback: <another-spec> }` — recursive; the
  fallback is itself a full value-spec.
- **template:** `{ template: "literal {path.to.field} more {@item.foo} on {@event.date}" }`
  — brace interpolation, with `@item`/`@event` semantics inside iterated rules.
- **composite timestamp:** `{ date_from: <spec>, time_from: <spec> }` →
  `YYYY-MM-DDTHH:MM:SS.sssZ`.
- **explicit timestamp parse:** `{ path: "...", parse_timestamp: "<strptime-format>" }`
  — parses with Python `datetime.strptime` and emits ISO 8601 in UTC (naive →
  assumed UTC; aware → converted). Combinable with `template:` to merge separate
  date and time columns.
- **arithmetic:** `{ multiply: [<spec>, <spec>, ...] }`.
- **lookup table:** `{ lookup: { key: <spec>, map: { "k1": "v1", ... }, default: <value> } }`.

**Timestamp policy (MANDATORY in the prompt):** if a column is already strict ISO
8601, use `transform: iso_millis`; otherwise emit `parse_timestamp` with exact
strptime directives that round-trip every sample value (the Fitabase export, for
example, uses `%m/%d/%Y %I:%M:%S %p`). The LLM is told never to guess directives.

### 5.4 Rule structure (`emit[]`)

Each rule has: `id`, `description`; `type` (an `EventType`); `category` (often a
value-spec, e.g. a `lookup`); `granularity`; one iteration mode; `timestamp`;
`payload`; optional `parent`; optional `extensions`; optional `quality`;
optional `quality_overrides`.

Iteration modes:
- (none) — one event per record.
- `iterate: <path>` — one event per element of a list; `@item`/`@event` apply.
- `iterate_object:` — expand an object's keys into one event per key.
  - `source` (optional path to the dict; defaults to the whole record),
  - `entries: [{ key, label }, ...]` — explicit keys, **or**
  - `all_keys: true` with optional `exclude: [...]` — auto-iterate every key
    (preferred for wide questionnaire CSVs).
  - Each iteration yields an item with `key`, `name` (= key), `question` (= key),
    `label`, `value`, referenced as `@item.name`, `@item.value`, etc.

**Payload triage (MANDATORY)** — the prompt forces a clear per-field decision so
data is neither lost nor duplicated:
- `payload.value`: the single headline data point (or `null` for a genuinely
  composite concept like blood pressure).
- `payload.components[]`: every *other* analytically relevant field — both true
  sub-measurements and descriptive fields an analyst would plot/aggregate/filter on.
  This is the default bucket.
- `extensions`: only genuine metadata/provenance (opaque IDs, audit timestamps).
  Keys are prefixed with the source name (e.g. `withings.attrib`).
- **HARD RULE:** a field used as `payload.value`/`raw_value` must not also appear as
  a component. The engine actually enforces this at load time (see §6.2).

`quality.flags` entries are either unconditional `{ code, severity, stage, message }`
or conditional `{ condition: { path, equals }, code, severity, stage, message }`.
If a source has no per-record timestamp, the guidance is to declare a literal ISO
string at `timestamp.start` and add a `SYNTHETIC_TIMESTAMP` info flag.

### 5.5 The downstream-stage blocks (`clean`, `validate`, `qualify`, `fhir`, `omop`)

These let one YAML configure the *whole* pipeline, not just the adapter:

- **`clean.heuristics`** — an ordered list (names or `{ name, ...params }`) over the
  closed enum `whitespace`, `timestamp_normalizer` (param `accept_formats`),
  `type_coercer`, `unit_inferrer` (param `mappings: { "<source>|<category>": "<unit>" }`).
  Listing a subset skips the rest; default chain is all four.
- **`validate.enabled`** — a subset of
  `[required_fields, timestamp_window, payload_shape, unit_whitelist, range]`
  (canonical order preserved). `validate.timestamp_window: { min, max }` overrides
  the global window (accepts ISO or `now±Xd/Xh`). `validate.categories.<cat>:` is a
  per-category overlay (shallow replace) of `expected_fields`, `unit_whitelist`,
  `range` on top of `quality_rules.yaml`.
- **`qualify.enabled`** — a subset of
  `[completeness, duplicates, outliers, conformance, plausibility]`, with tunables
  `outliers: { hampel_k: 3.5, min_group_size: 5 }`,
  `duplicates: { fields: [...], value_round_digits: 3 }`,
  `plausibility: { warning_count_for_review: 1 }`,
  `completeness: { expected_fields: { <cat>: [...] } }`.
- **`fhir`** — `enabled`, `bundle_type` (`transaction`/`collection`), `include`
  (subset of `[Patient, Observation, Device, Provenance, Questionnaire]`; default
  `[Patient, Observation, Questionnaire]`).
- **`omop`** — `enabled`, `include` (subset of
  `[person, measurement, observation, device_exposure, observation_period]`;
  default all). The prompt instructs: always include an `omop:` block whenever you
  include a `fhir:` block.

### 5.6 Two worked examples (verbatim few-shot configs)

These are the actual files embedded as few-shot examples (`backend/configs/examples/`).

**`withings-body-scale.yaml`** — demonstrates `lookup` for both `category` and
`unit`, `transform: iso_millis`, multi-type polymorphism, source-prefixed
`extensions`, and *conditional* quality flags keyed on `attrib`:

```yaml
adapter:
  id: "withings-body-scale-v1"
  version: "1.0.0"
  description: "Withings Body+ scale measurements (Weight, Height, Fat Ratio, Muscle Mass, etc.)"
match:
  source: "withings"
  record:
    - { field: "userId", exists: true }
    - { field: "measurementDateTime", exists: true }
    - { field: "measurementValue", exists: true }
    - { field: "measurementType", type: "object" }
    - field: "measurementType.typeDescription"
      in: ["Weight","Height","Fat Free Mass","Fat Ratio","Fat Mass Weight","Muscle Mass",
           "Bone Mass","Hydration","Heart Rate","Diastolic Blood Pressure",
           "Systolic Blood Pressure","SP02","Pulse Wave Velocity"]
defaults:
  subject_id: { path: "userId" }
  context:
    source: "withings"
    modality: "scale"
    device: null
    source_measurement_type: { path: "measurementType.typeDescription" }
  stage: "structured"
  source_record_id:
    template: "withings:{userId}:{measurementType.typeValue}:{measurementDateTime}"
emit:
  - id: "body-measurement"
    description: "One scalar body measurement from a Withings scale"
    type: "measurement"
    granularity: "instant"
    category:
      lookup:
        key: { path: "measurementType.typeDescription" }
        map:
          "Weight": "weight"
          "Height": "height"
          "Fat Free Mass": "fat-free-mass"
          "Fat Ratio": "body-fat-ratio"
          "Fat Mass Weight": "fat-mass"
          "Muscle Mass": "muscle-mass"
          "Bone Mass": "bone-mass"
          "Hydration": "body-water"
          "Heart Rate": "heart-rate"
          "Diastolic Blood Pressure": "blood-pressure-diastolic"
          "Systolic Blood Pressure": "blood-pressure-systolic"
          "SP02": "spo2"
          "Pulse Wave Velocity": "pulse-wave-velocity"
        default: "unknown"
    timestamp:
      start: { path: "measurementDateTime", transform: "iso_millis" }
    payload:
      value: { path: "measurementValue" }
      raw_value: { path: "measurementValue" }
      unit:
        lookup:
          key: { path: "measurementType.typeDescription" }
          map:
            "Weight": "kg"
            "Height": "m"
            "Fat Free Mass": "kg"
            "Fat Ratio": "%"
            "Fat Mass Weight": "kg"
            "Muscle Mass": "kg"
            "Bone Mass": "kg"
            "Hydration": "kg"
            "Heart Rate": "bpm"
            "Diastolic Blood Pressure": "mmHg"
            "Systolic Blood Pressure": "mmHg"
            "SP02": "%"
            "Pulse Wave Velocity": "m/s"
          default: null
      label: { path: "measurementType.typeDescription" }
    extensions:
      withings.typeValue:        { path: "measurementType.typeValue" }
      withings.attrib:           { path: "attrib" }
      withings.createdDateTime:  { path: "createdDateTime" }
      withings.modifiedDateTime: { path: "modifiedDateTime" }
    quality:
      flags:
        - condition: { path: "attrib", equals: 2 }
          code: "MANUAL_ENTRY"
          severity: "info"
          stage: "structured"
          message: "Measurement entered manually by the user (attrib=2)"
        - condition: { path: "attrib", equals: 1 }
          code: "AMBIGUOUS_SUBJECT"
          severity: "warning"
          stage: "structured"
          message: "Withings flagged subject attribution as ambiguous (attrib=1)"
clean:
  heuristics:
    - whitespace
    - timestamp_normalizer
    - type_coercer
    - { name: unit_inferrer, mappings: { "withings|body-water": "kg" } }
validate:
  enabled: [required_fields, timestamp_window, payload_shape, unit_whitelist, range]
  timestamp_window: { min: "2010-01-01", max: "now+1d" }
qualify:
  enabled: [completeness, duplicates, outliers, conformance, plausibility]
  outliers:     { hampel_k: 3.5, min_group_size: 5 }
  duplicates:   { fields: [subject_id, category, timestamp, payload.value], value_round_digits: 3 }
  plausibility: { warning_count_for_review: 1 }
fhir:
  enabled: true
  bundle_type: transaction
  include: [Patient, Observation, Device, Provenance]
omop:
  enabled: true
  include: [person, measurement, observation, device_exposure, observation_period]
```

**`mhealth-app-usage-daily-v1.yaml`** (excerpt) — demonstrates several `emit`
rules with `iterate`, mixing `@item` and `@event` references, type polymorphism
(`event`/`observation`/`survey`), and a `SYNTHETIC_TIMESTAMP` flag:

```yaml
emit:
  - id: exercise-completed
    type: event
    category: exercise-completed
    granularity: instant
    iterate: metrics.exercises.completed
    timestamp:
      start: { path: '@item.completedAt', transform: iso_millis }
    payload:
      value: { path: '@item.exerciseId' }
      raw_value: { path: '@item.exerciseId' }
      unit: null
      label: exerciseId
      components:
        - { name: week, value: { path: '@item.week' } }
        - { name: day,  value: { path: '@item.day' } }
    extensions:
      mhealth.exerciseId: { path: '@item.exerciseId' }
      mhealth.completedAt: { path: '@item.completedAt' }
  - id: recipe-favorited
    type: observation
    category: recipe-favorited
    iterate: metrics.recipes.favorited
    timestamp:
      start: { path: '@event.timestamp', transform: iso_millis }   # reach back up to the record
    payload:
      value: { path: '@item.recipeId' }
      raw_value: { path: '@item.recipeId' }
      label: recipeId
  - id: profile-question-answered
    type: survey
    category: profile-question-answered
    iterate: metrics.assessments.profileQuestionsAnswered
    timestamp:
      start: { path: '@event.timestamp', transform: iso_millis }
    payload:
      value: { path: '@item' }
      raw_value: { path: '@item' }
      label: profileQuestionsAnswered
    quality:
      flags:
        - code: SYNTHETIC_TIMESTAMP
          severity: info
          stage: structured
          message: No per-item timestamp; the parent record timestamp is used.
```

---

## 6. The DSL engine — `ConfigAdapter`

`backend/pipeline/adapter/config_adapter.py` (≈760 lines) is the generic engine
that *executes* the DSL. It is a `BaseAdapter` subclass holding the parsed config.
It is **Tier-1**: no source-specific code, everything is data-driven.

### 6.1 The expression evaluator

Three module-level functions do the heavy lifting:

- **`_resolve_path(obj, path)`** — resolves a dot-notation path with `[index]`
  array access. `re.split(r"\.", path)` splits on dots; each part is matched against
  `^(.+?)\[(\d+)\]$` to detect an index. `"."`, `"@"` and `""` resolve to the object
  itself. Returns `None` on any miss (dict key absent, index out of range, walking
  into a non-dict).
- **`_apply_transform(value, transform)`** — the scalar transform registry,
  implemented as an if/elif chain (string `value` is coerced via `str(value)` first;
  `None` short-circuits to `None`):
  - `start_of_day` → `"{date[:10]}T00:00:00.000Z"`
  - `end_of_day` → `"{date[:10]}T23:59:59.999Z"`
  - `iso_date` → `"{date[:10]}T00:00:00.000Z"`
  - `iso_millis` → normalises an ISO string to millisecond precision, padding/truncating
    the fractional seconds to exactly 3 digits and preserving the timezone token
    (via a regex `^(.*?)(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$`).
  - `to_int` → `int(s)` or `None` on failure.
  - `to_float` → `float(s)` or `None` on failure.
- **`_parse_timestamp(value, format_str)`** — `datetime.strptime` with an explicit
  format, emitting ISO 8601 millisecond UTC. Naive results are treated as UTC
  (matching the cleaner's `TIMEZONE_ASSUMED_UTC` convention); aware results are
  converted. On parse failure it logs a warning and returns the **original value
  unchanged** so the validator can flag it downstream — i.e. the engine never
  raises on bad data.

**`_resolve_value(spec, record, item=None, *, record_index=None)`** is the
dispatcher that implements every value-spec form from §5.3. Non-dict specs are
literals (returned as-is). For a `path` spec it special-cases `@record_index`,
`@event`/`@event.<sub>` (resolves against the whole record), `@item`/`@item.<sub>`
(resolves against the current iteration element; returns the spec's `fallback` if
no item), then applies `fallback` (recursively), `transform`, and `parse_timestamp`
in that order. It also handles `date_from`+`time_from`, `multiply`, `template`
(with a regex replacer honouring `@record_index`/`@event`/`@item`), and `lookup`.

### 6.2 Matching and load-time validation

- **`can_handle(metadata, record)`** evaluates every `match.record` clause via
  `_evaluate_predicate`, which delegates to **`_explain_predicate`** — the latter
  returns `(verb, expected, actual)` of the *first failing clause* (or `None` if all
  pass). The same explainer powers `explain_no_match(...)`, which turns a miss into a
  `SkippedReason` with a precise message (e.g. ``Record failed match.record clause
  `dataType equals 'x'` (actual: 'y')``). Predicate verbs supported:
  `equals`, `in`, `exists`, `type` (`_check_type` understands
  object/array/string/integer/number/boolean/null and uses `try_coerce_numeric` so a
  numeric *string* satisfies `integer`/`number`), and `non_empty`.
- **`_strip_redundant_components()`** runs at construction. It enforces the "a value
  is never also a component" hard rule by removing any component whose `value` spec
  is *identical* to the rule's `payload.value` spec, recording the dropped names per
  rule so the adapter can report the drop through diagnostics
  (`redundant_component_dropped`). This prevents a FHIR Observation from carrying the
  same datum in both `value[x]` and a `component[]`, and prevents the mapper from
  surfacing the same concept twice.
- The constructor also parses the sibling blocks into typed config objects:
  `CleanConfig`, `ValidateConfig`, `QualifyConfig`, `FhirConfig`, `OmopConfig`,
  exposed as `clean_block`/`validate_block`/`qualify_block`/`fhir_block`/`omop_block`
  (each `None` when the block is omitted → stage default behaviour).

### 6.3 Rule execution

`transform(metadata, record, *, record_index, collector)` mints a `group_id` and an
`ingested_at` shared by all events from this record, then runs each rule via
`_execute_rule`, tracking per-rule event lists so a rule's `parent` reference can be
resolved (the parent's first event id becomes `parent_event_id`).

`_execute_rule` chooses an iteration mode:
- `iterate` — resolves the path; records a precise `SkippedReason` if it is `None`
  (`iterate_path_none`), not a list (`iterate_not_list`), or empty (`iterate_empty`);
  otherwise builds one event per element.
- `iterate_object` — resolves the source dict (root, a string path, or a
  `{path}` spec); records `iterate_object_source_none/_invalid/_not_dict` on misses;
  then iterates either the explicit `entries` (recording
  `iterate_object_keys_missing` for absent keys) or `all_keys` minus `exclude`. Each
  iteration synthesises an item `{ key, name, question, label, value }`.
- (neither) — a single event.

`_build_event(...)` constructs the `CanonicalEvent` field by field, all through
`_resolve_value`:
- `subject_id` from `defaults.subject_id` (stringified; `""` if `None`).
- `timestamp`/`timestamp_end`/`duration_seconds` from `rule.timestamp.{start,end,duration_seconds}`.
- `payload.value`/`raw_value`/`unit`/`label`, and `components` (each
  `Component(name, value, unit?)`).
- `context.source` (falls back to `match.source`), `modality` (coerced to the
  `Modality` enum; unknown strings become `Modality.UNKNOWN`), `device` (falls back
  to `metadata.device`), `source_measurement_type`.
- `extensions` from `rule.extensions`; `quality_overrides` are stashed under
  `extensions["_quality_override"]` for the validator to consume (see §9).
- conditional/unconditional `quality.flags` — a conditional flag is emitted only
  when `record[cond.path] == cond.equals`.
- `source_record_id` from `defaults.source_record_id`, or a default template
  `"{source}:{userId}:{measurementType}:{measurementDateTime}"` if none is given.
- `type`/`category`/`granularity` resolved (category defaults to `"unknown"`,
  granularity to `"unknown"`).
- `provenance` carries `group_id`, `parent_event_id`, `adapter` (= `adapter.id`),
  `adapter_version`.
- `mapping=Mapping()` (empty — populated later by the mapper).
- `stage` from `defaults.stage` (default `"structured"`).

---

## 7. Adapter diagnostics

`backend/pipeline/adapter/diagnostics.py` exists because an LLM-generated config
can silently emit zero events (a path resolves to `None`, an iterate target is the
wrong type, a match predicate excludes everything). Rather than fail opaquely, the
adapter records **why** and surfaces it to the UI so the user can fix the YAML.

- **`SkippedReason`** — `{ code, record_index, detail, rule_id?, path?, expected?,
  actual?, record_keys? }`. `record_keys` lists the record's top-level keys to orient
  the user when a path didn't resolve.
- **`RuleDiagnostic`** — per-rule `{ records_seen, events_emitted, skipped_reasons }`.
- **`AdapterDiagnostics`** — totals `{ records_total, records_matched,
  records_unmatched, events_emitted, rules[], predicate_failures[] }`.
- **`DiagnosticsCollector`** — threaded through the adapter run; record-aware and
  rule-aware (`start_record`/`record_matched`/`record_unmatched`,
  `start_rule`/`end_rule`, `record_skip`, `finalize`).

Two caps keep the payload bounded on a broken config processing thousands of
records: **`MAX_REASONS_PER_RULE = 3`** and **`MAX_PREDICATE_FAILURES = 5`** — the
first few examples are enough to diagnose. The diagnostics are returned in the
`/api/transform` response and feed the `/api/suggest-config-fix` flow.

---

## 8. The cleaner stage (CLEANED)

`backend/pipeline/cleaner/`. The cleaner runs a chain of **heuristics**, each a
`BaseHeuristic` whose contract is *Event → Event, may mutate, may append quality
flags, never drops*. The default chain (when `clean` is omitted) is, in order:

1. **`WhitespaceStripper`** — strips leading/trailing whitespace from string
   fields (`payload.label`, `payload.value`, `payload.raw_value`) only when they are
   already `str`. Silent (no flags).
2. **`TimestampNormalizer`** — normalises `timestamp`/`timestamp_end` to ISO 8601
   with a `Z`. Built-in regexes recognise full ISO and date-only forms. Behaviour and
   flags:
   - already-ISO-with-`Z` → unchanged;
   - ISO without timezone → append `Z`, flag **`TIMEZONE_ASSUMED_UTC`** (info);
   - date-only `YYYY-MM-DD` → expand to start-of-day, flag **`DATE_ONLY_TIMESTAMP`**
     (info);
   - otherwise try each `accept_formats` strptime pattern (param), converting to UTC,
     flag **`TIMESTAMP_FORMAT_PARSED`** (info).
3. **`TypeCoercer`** — coerces numeric strings on `payload.value` and each
   `components[].value` via `try_coerce_numeric`; if any coercion occurred, flags
   **`VALUE_COERCED`** (info).
4. **`UnitInferrer`** — fills `payload.unit` when `None`, keyed on
   `(context.source, category)`, from a hardcoded default table (e.g.
   `("fitbit","heart-rate")→"bpm"`, `("withings","weight")→"kg"`) merged with the
   config's `mappings: { "source|category": "unit" }`; flags **`UNIT_INFERRED`**
   (info).

`CleanConfig` (from `clean.heuristics`) lets the YAML reorder, subset or parameterise
the chain. The stage sets `stage = Stage.CLEANED`.

---

## 9. The validator stage (VALIDATED)

`backend/pipeline/validator/`. Validators **assert only — they never mutate values**
and return `list[QualityFlag]`. The `ValidationRunner` loads `quality_rules.yaml`
(via `domain.rules.load_rules`, cached in-process), merges any per-config
`validate` overlay, runs the validators in a fixed canonical order, and de-dups
flags by `(code, stage, message)` before appending. The stage is set to
`Stage.VALIDATED`. The five built-ins:

| Validator | Check | Flag code(s) · severity |
|---|---|---|
| `RequiredFieldsValidator` | `subject_id`, `timestamp`, `category` (not `"unknown"`), `type` present | `MISSING_REQUIRED_FIELD` · **error** |
| `TimestampValidator` | parseable ISO 8601; within `timestamp_window` (`now±Xd/Xh` understood) | `TIMESTAMP_UNPARSEABLE` · **error**; `TIMESTAMP_OUT_OF_WINDOW` · **warning** |
| `PayloadValidator` | per-`EventType` minimum payload (value / components / label / duration as appropriate) | `PAYLOAD_EMPTY` · **error** |
| `UnitValidator` | `payload.unit` ∈ category `unit_whitelist` (when one is defined and unit non-null) | `UNIT_NOT_IN_WHITELIST` · **warning** |
| `RangeValidator` | numeric `payload.value` within category `range.{min,max}` | code & severity come from `range.on_violation` (e.g. `HR_OUT_OF_RANGE` · warning) |

Per-rule narrowing flows in through `extensions["_quality_override"]` (set by the
adapter from `quality_overrides`), which the runner reads as a per-event overlay on
top of the category rules. Consistent with *tag, don't drop*, a failed event stays
in the stream carrying its `ERROR`/`WARNING` flags. The adapter-declared
conditional flags from §6.3 are de-duped against validator output by the same
`(code, stage, message)` key.

---

## 10. The qualifier stage (QUALIFIED)

`backend/pipeline/qualifier/`. The qualifier performs **cross-event** analysis and
then derives the three Kahn-aligned verdicts. Checks (each toggleable via
`qualify.enabled`):

1. **Completeness** — for each event, `ratio = present_field_count /
   expected_field_count` over the category's `expected_fields` (default
   `["subject_id","timestamp","payload.value"]`), resolving dotted paths and treating
   null/empty as absent. Stored on `quality.completeness` plus the two counters.
   Metrics only — no flags.
2. **Duplicates** — a fingerprint over configurable fields
   (default `[subject_id, category, timestamp, payload.value]`, floats rounded to
   `value_round_digits=3`). First occurrence is clean; each later identical
   fingerprint gets **`DUPLICATE_EVENT`** (warning).
3. **Outliers (Hampel)** — grouping by `(subject_id, category)` over numeric
   `payload.value`. With `k = hampel_k` (default **3.5**) and `min_group_size`
   (default **5**): groups below the minimum emit **`OUTLIER_INSUFFICIENT_DATA`**
   (info) and skip; otherwise each point with `|x − median| / MAD > k` gets
   **`OUTLIER_HAMPEL`** (warning). Groups where MAD collapses to 0 are skipped. The
   median-absolute-deviation Hampel identifier is robust to the heavy tails typical
   of wearable data; the `min_group_size = 5` floor exists precisely because MAD
   collapses to 0 on tiny groups and would otherwise flag everything — it should not
   be lowered without statistical justification.
4. **Conformance** — `quality.conformance = "issues"` if any conformance-class flag
   (codes prefixed `RANGE_`/`UNIT_`/`TIMESTAMP_`/`MISSING_`/`PAYLOAD_`, plus the
   explicit per-category range codes such as `HR_OUT_OF_RANGE`) has non-info
   severity; else `"ok"`.
5. **Plausibility** — `"exclude"` if any `ERROR` flag exists; else `"review"` if the
   `WARNING` count ≥ `warning_count_for_review` (default 1); else `"ok"`.

The stage returns a **stats dict** summarising the batch — counts, the subject list,
a flag-code histogram, severity/stage/plausibility/conformance tallies — which is
surfaced in the API response. The stage is set to `Stage.QUALIFIED`.

**Documented limitation:** because the API is stateless, outlier detection only
sees the current request's events. With a persistence layer it could use
cross-request baselines.

---

## 11. Quality rules (`quality_rules.yaml`)

The global per-category defaults consulted by the validator and qualifier live in
`backend/configs/quality_rules.yaml`. The schema per category is
`expected_fields` (completeness), `unit_whitelist` (UnitValidator), and
`range: { min, max, on_violation: { severity, code } }` (RangeValidator);
`timestamp_window` and `plausibility_thresholds` are global. Verbatim excerpt:

```yaml
timestamp_window:
  min: "2010-01-01T00:00:00Z"
  max: "now+1d"

plausibility_thresholds:
  warning_count_for_review: 1

categories:
  heart-rate:
    expected_fields: ["subject_id", "timestamp", "payload.value", "payload.unit"]
    unit_whitelist: ["bpm", "count/min"]
    range: { min: 30, max: 220, on_violation: { severity: "warning", code: "HR_OUT_OF_RANGE" } }
  heart-rate-zone:
    expected_fields: ["subject_id", "timestamp", "payload.components"]
    range: { min: 0, max: 1440, on_violation: { severity: "warning", code: "HR_ZONE_MINUTES_OUT_OF_RANGE" } }
  steps:
    expected_fields: ["subject_id", "timestamp", "payload.value"]
    unit_whitelist: ["count"]
    range: { min: 0, max: 100000, on_violation: { severity: "warning", code: "STEPS_OUT_OF_RANGE" } }
  weight:
    expected_fields: ["subject_id", "timestamp", "payload.value", "payload.unit"]
    unit_whitelist: ["kg", "lb", "g"]
    range: { min: 0, max: 500, on_violation: { severity: "warning", code: "WEIGHT_OUT_OF_RANGE" } }
  height:
    expected_fields: ["subject_id", "timestamp", "payload.value", "payload.unit"]
    unit_whitelist: ["m", "cm"]
    range: { min: 0, max: 3, on_violation: { severity: "warning", code: "HEIGHT_OUT_OF_RANGE" } }
  body-fat-ratio:
    expected_fields: ["subject_id", "timestamp", "payload.value", "payload.unit"]
    unit_whitelist: ["%"]
    range: { min: 0, max: 100, on_violation: { severity: "warning", code: "BODY_FAT_OUT_OF_RANGE" } }
```

The file additionally covers `distance`, `calories`, `floors`, `elevation`, and
further Withings/body-composition and blood-pressure/SpO2 categories following the
same schema. The heart-rate `[30, 220]` bound aligns with maximum-heart-rate norms
(cf. Tanaka et al. 2001); the writer can cite that where physiological ranges are
discussed. An adapter YAML narrows any of these per emit-rule via
`quality_overrides:`, or per-category via `validate.categories`.

---

## 12. The mapper stage (MAPPED)

`backend/pipeline/mapper/`. The mapper performs the `QUALIFIED → MAPPED` transition:
it detects **concept slots** and applies user-selected terminology bindings. It
exists because wearable/PGHD data is massively repetitive — a single day of Fitbit
heart-rate can be ~86,400 events all needing the same LOINC code — so the user
should pick a code **once per slot** and have it applied to thousands of events.

### Slot detection

`detect_slots(events, mappings)` walks the events once and groups them by a slot
**key** (`keys.py`), deduplicating:
- **code** slot — `"code|{category}|{label}"` — the headline measurement. Components
  share this `code|` namespace (`"code|{category}|{component.name}"`) so an identical
  concept maps to one slot.
- **unit** slot — `"unit|{unit}"` — the unit of measure (UCUM target).
- **category** slot — `"category|{text}"` — the FHIR Observation category bucket.

Each `ConceptSlot` carries `{ key, kind, label, count, sample, suggested_system,
default_coding, current_mapping }`. `suggested_system` is inferred per kind:
`http://loinc.org` for code, `http://unitsofmeasure.org` for unit, and the HL7
`observation-category` code system for category. Category slots get auto-bound
default codings (vital-signs/activity/exam/survey) even without a user pick.

### Binding

`run(events, mappings)` applies the user-supplied `concept_mappings` (keyed by slot
key). A **code** binding populates the public `event.mapping`
(`standard_code`/`standard_system`/`standard_display`/`method`/`concept_id`/
`standard_concept`); **unit / component / category** bindings go into the private
`event.extensions["_concept_codings"]` bag (stripped by `to_dict()`, read by the
FHIR and OMOP builders). Every event is stamped `Stage.MAPPED` regardless of whether
a binding applied, so downstream stages see a uniform state. The mapper returns
stats `{ slot_count, unbound_count, events_bound, slots[] }`; `unbound_count`
counts code+unit slots still without a mapping and drives the UI's "needs mapping"
indicator.

---

## 13. FHIR R4 projection (STANDARDIZED)

`backend/pipeline/fhir/` builds an HL7 FHIR R4 **Bundle** from the mapped events.
FHIR is the *exchange* standard: self-describing resources connected by references,
packaged in a Bundle. The builder stamps `Stage.STANDARDIZED` on every event.

### Resource construction

- **Patient** — one per `subject_id`; a PII-free stub with an `identifier`
  (`system: "urn:harmonia:subject"`, `value: subject_id`).
- **Observation** — for `type ∈ {measurement, observation, event, session, summary}`.
- **QuestionnaireResponse** — for `type = survey`; each component becomes an
  `item[]` with `linkId` and `answer[]`.
- **Questionnaire** — one definition per unique survey category (when included);
  its `item[]` is inferred from the first survey event's components, the item `type`
  inferred from the value (`integer`/`decimal`/`boolean`/`string`). Each
  `QuestionnaireResponse` links back via `questionnaire`.
- **Device** — one per `(source, device)` pair; referenced from Observations.
- **Provenance** — one resource referencing all observations, recording which
  adapter/version produced them.

### Mapping rules

- **type → resource:** as above.
- **plausibility → status:** `exclude → entered-in-error`, `review → amended`,
  else `final` (for `QuestionnaireResponse`: `entered-in-error` / `amended` /
  `completed`).
- **timestamps → effective[x]:** both start+end → `effectivePeriod`; start only →
  `effectiveDateTime`.
- **value → value[x]:** `bool → valueBoolean`; `int|float → valueQuantity`
  (`{value, unit, system, code}` where the UCUM coding comes from the bound unit);
  otherwise `valueString`.
- **components → `component[]`** (Observation) or **`item[]`**
  (QuestionnaireResponse), each with its own code and value[x].
- **quality flags → `note[]`** as `"[severity/code] message"` — the audit trail is
  preserved in FHIR without extensions.
- **category bucketing:** `survey → "survey"`, `observation → "exam"`,
  `event|session → "activity"`; vital-sign categories (weight, height, bmi,
  heart-rate, blood-pressure, respiratory-rate, body-temperature, spo2,
  oxygen-saturation) → `"vital-signs"`; activity categories (steps, distance,
  calories, intensity, active-minutes, exercise, workout, session, sleep,
  sleep-stage) → `"activity"`; fallback `"exam"`.
- **CodeableConcepts** always carry `text`; a `coding[]` array is added only when
  the mapper bound a code (FHIR R4 permits text-only CodeableConcepts — full
  automated terminology binding is left to the mapper/user).

### Reference integrity (`refs.py`)

All intra-bundle references are **UUID5** derived from a single pinned namespace
(`_NS = a3f1c4e8-7d61-4f2c-9a3b-3e8d5b1c0f10`) and stable seeds:
`subject:{id}`, `device:{source}|{device}`, `observation:{event_id}`,
`questionnaire:{category}`, `provenance:{group_id}`. This guarantees identical
inputs produce identical URIs across runs (idempotent `PUT`) and that every
`urn:uuid:` reference resolves to a `fullUrl` in the same bundle. A post-build
`_verify_references` pass walks the bundle and reports dangling references.

### Config & output

`FhirConfig` = `{ enabled (default true), bundle_type ("transaction"/"collection"),
include }`. In a `transaction` bundle each entry gets a `request` block (`PUT` for
Patient, `POST` for others), making it directly POST-able to a FHIR server; a
`collection` omits the request slice. `run()` returns stats containing the
serialized `bundle`, `resource_count`, an approximate `size_bytes`, and the list of
any dangling references.

---

## 14. OMOP CDM v5.4 projection

`backend/pipeline/omop/` projects the mapped events into OMOP CDM tables. OMOP is
the *analytics* standard: a person-centric relational schema where every clinical
fact occupies one row carrying a **standard `concept_id`** from the OHDSI
vocabularies. Tables emitted: `person`, `measurement`, `observation`,
`device_exposure`, `observation_period` (plus a `concept` table for any custom
concepts). The OMOP builder does **not** further mutate the canonical events.

### Identity

- **`person_id`** — deterministic: the first 4 bytes of `SHA-256(subject_id)`
  interpreted big-endian, taken modulo 2³¹ to fit OMOP's integer bounds.
  `person_source_value` preserves the original `subject_id`. Demographics are
  unknown for wearable data, so `gender/race/ethnicity_concept_id = 0`.
- **Row IDs** are sequential within a request (a real warehouse assigns its own on
  INSERT).

### Concept resolution — the central challenge

OMOP requires a `concept_id` for every row (unlike FHIR's tolerant text-only
codings), so coverage is the bottleneck. The builder collects unique `(system, code)`
pairs from `event.mapping` and `event.extensions["_concept_codings"]`, filters to a
set of resolvable systems (LOINC, SNOMED, UCUM, RxNorm, ICD-10-CM/10/9-CM, CPT4,
ATC), and batch-resolves them via the **OMOPHub FHIR Resolver**
(`POST /v1/fhir/resolve/batch`). Each result yields a `source_concept`, a
`standard_concept` (the OHDSI standard it maps to, possibly different), a
`target_table`, and a `mapping_type` (`direct`/`mapped`/`semantic_match`/
`unmapped`). The resolver client caches results in-process (≈600 s TTL), chunks
batches (~100 codings), and degrades to per-coding calls on a batch error.

Routing decision (`_pick_concepts`): a user-picked `concept_id` wins; otherwise the
resolver's standard concept; failing that the source concept (`source_only`);
failing that a deterministic **custom 2-billion concept** is minted
(`concept_id = 2_000_000_000 + hash(system|code) mod 1e8 + 1`, vocabulary
`Custom:{source}`) per OHDSI guidance for unmapped source codes. If nothing
resolves at all, the row is emitted with **`concept_id = 0`** ("No matching
concept") and an entry is added to the **`unmapped[]`** audit list — consistent with
*tag, don't drop*.

When the resolver returns no `target_table`, a fallback heuristic routes:
`survey → observation`; numeric measurement/summary/observation → `measurement`;
everything else → `observation`.

### Other mapping rules

- **components → separate rows.** OMOP has no `component` construct, so each
  `payload.components[]` entry becomes its own row with
  `measurement_source_value = "{category}.{component_name}"` (dot notation preserving
  the parent relationship). A blood-pressure event thus yields one FHIR Observation
  (2 components) but multiple OMOP rows.
- **`*_type_concept_id`** records *how* the data was captured, derived from
  `context.modality`. These are resolved dynamically via OMOPHub's semantic-bulk
  search filtered to `concept_class_id = "Type Concept"`, with hardcoded fallbacks
  when OMOPHub is unavailable: wearable/sensor/app/game/vr → **32865** (patient
  self-report), scale → **705183** (patient self-tested), survey → **32862**
  (patient filled survey), unknown → **32817** (EHR).
- **plausibility filtering.** Events with `quality.plausibility = "exclude"` are
  **skipped entirely** — the single, deliberate exception to *tag, don't drop*,
  because including implausible data would contaminate cohort queries. Such events
  remain available via the canonical model and the FHIR bundle.
- **device_exposure** — one row per unique `(source, device)` spanning the
  earliest-to-latest event date (`device_concept_id = 0`; there is no OHDSI
  vocabulary for consumer wearable models).
- **observation_period** — one row per person spanning earliest-to-latest date
  (required by analytics tools such as ATLAS).

`OmopConfig` = `{ enabled (default true), include }`. `run()` returns a dict keyed by
table name (each value a list of row dicts) plus resolution statistics (total
codings, resolved/failed counts, `mapping_types` histogram) and an `unmapped[]`
audit list.

### FHIR vs OMOP — the structural contrast (for the chapter)

| Aspect | FHIR R4 | OMOP CDM v5.4 |
|---|---|---|
| Purpose | exchange / interoperability | analytics / observational research |
| Model | document (self-describing resources) | relational (tables + vocabulary) |
| Terminology | text-only CodeableConcept allowed | mandatory `concept_id` (0 = unmapped) |
| Components | nested `component[]` | flattened to separate rows |
| Surveys | Questionnaire + QuestionnaireResponse | rows in `observation` |
| Excluded events | emitted as `entered-in-error` | skipped entirely |
| Quality flags | preserved as `note[]` | not projected |
| Provenance | `Provenance` resource | no standard table (partly via source_value) |
| Identity | UUID5 (idempotent PUT) | integer IDs (sequential) |

---

## 15. Terminology subsystem (OMOPHub)

`backend/api/terminology.py` implements `OmopHubClient`, a semantic-search client
over the OMOPHub hosted OHDSI/ATHENA vocabulary service (base
`https://api.omophub.com/v1`, Bearer auth from `OMOPHUB_API_KEY`). It powers both
`/api/terminology/search` and the LLM concept-suggestion tool.

- **`search(system, query, max_results)`** → `GET /concepts/semantic-search` with a
  vocabulary filter and `threshold=0.3`. Returns `{ system, code, display,
  standard_concept, concept_id? }`.
- **`bulk_search(searches, defaults)`** → `POST /search/semantic-bulk`, batching up
  to ~25 searches and degrading to per-search calls on error.

It maps the frontend's short system names to OMOPHub vocabulary IDs
(`loinc→LOINC`, `ucum→UCUM`, `snomed→SNOMED`, `rxnorm→RxNorm`, `icd10→ICD10CM`,
`cpt→CPT4`) and OMOPHub vocabulary IDs to FHIR system URIs (`LOINC→http://loinc.org`,
`UCUM→http://unitsofmeasure.org`, `SNOMED→http://snomed.info/sct`, etc.; unknown →
`urn:omophub:vocab:{vocab}`). It filters out non-clinical LOINC concept classes
(Hierarchy/Component/System/Method/Property/Time Aspect/Scale), enforces a minimum
inter-request interval (~0.5 s) and retries on HTTP 429 using `Retry-After`.
Failures raise `TerminologyError` (surfaced as HTTP 502). The API key is read at
call time so a running server picks up env changes.

When `OMOPHUB_API_KEY` is unset, terminology search and OMOP domain routing are
unavailable; the pipeline still runs but OMOP rows fall back to `concept_id = 0`.

---

## 16. LLM subsystem

### Client abstraction

`api/llm/client.py` defines a minimal `LLMClient` protocol (`generate(system, user)
-> str`, and `generate_with_tools(...)`). `api/llm/langchain_client.py` implements
it over LangChain's `init_chat_model`, selecting provider/model from env
(`LLM_PROVIDER` default `anthropic`, `LLM_MODEL` default `claude-opus-4-7`), with
`temperature = 0.0` and `max_tokens = 8192`. It validates that the matching API key
(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GOOGLE_API_KEY`) is present and raises
otherwise. `generate_with_tools` runs an agentic loop (up to `max_iterations = 10`):
invoke → if `tool_calls`, execute each and append `ToolMessage`s → repeat; after the
cap it asks once more for a final JSON answer.

### The four prompt flows (`api/prompts.py`)

All four share the *same* system-prompt scaffold: the **canonical model source**
(the actual `domain/models.py` text), the **full DSL spec** (`DSL_OVERVIEW`,
reproduced in §5), and the **few-shot corpus** (`withings-body-scale.yaml` +
`fitabase-fitbit-csv.yaml`, loaded from disk). They differ only in framing and user
prompt:

1. **Generate** (`/api/generate-config`) — `build_system_prompt` + `build_user_prompt`.
   The user prompt supplies the data description, optional hints, the required
   `match.source`, a truncated JSON sample (≤20 KB, first 3 array elements), and any
   uploaded **descriptor** files (schemas/specs, ≤32 KB each, rendered as fenced
   blocks). It closes by instructing the model to derive a rigid `match.record`.
2. **Repair** (`/api/suggest-config-fix`) — `build_fix_*`. Given the failing YAML,
   the diagnostics JSON, and one sample record, the model returns a corrected YAML.
   It is *not* saved — the frontend previews it first.
3. **Edit** (`/api/edit-config`) — `build_edit_*`. Applies a natural-language change
   to a working config and returns the full updated YAML; previewed as a diff.
4. **Concept suggestion** (`/api/suggest-concepts`) — `build_concept_suggest_*`. A
   "clinical terminology specialist" prompt that is given the concept slots and a
   `search_terminology` tool. Its hard rule: *never invent codes; every returned code
   must be copied verbatim from a tool result.* It returns JSON
   `{ suggestions: {key: {system, code, display, confidence}}, no_matches: {...} }`.

`strip_code_fence` defensively removes a leading ```` ```yaml ```` / ```` ``` ````
fence and trailing fence from model output before parsing.

### Anti-hallucination guard (`/api/suggest-concepts`)

The route wraps the `search_terminology` tool so that **every** `(system, code)` the
tool actually returned is recorded in a `seen_codes` set (and its
`standard_concept`). After the model responds, any suggested coding whose
`(system, code)` is **not** in `seen_codes` is dropped and logged as hallucinated.
Confidence is validated against `{high, medium, low}`; category slots are excluded
(they already have defaults). This is a concrete, defensible safeguard worth
highlighting in the thesis.

`api/main.py` assembles the app (`FastAPI(title="Harmonia API", version="0.3.0")`),
adds CORS from `ALLOWED_ORIGIN` (default `http://localhost:3000`,
`allow_credentials=False`, all methods/headers), and includes the router.

---

## 17. HTTP API reference

All routes are under `/api` (`backend/api/routes.py`).

| Method · Path | Request | Response | Notes |
|---|---|---|---|
| `GET /healthz` | — | `{ ok: true }` | liveness |
| `POST /generate-config` | `{ data, description, hints?, source?, descriptors? }` | `{ id, yaml }` | LLM-generates a config, validates the YAML parses and that `ConfigAdapter.from_dict` accepts it, **saves** it. 502 on LLM/parse failure. |
| `GET /configs` | — | `ConfigSummary[]` | lists saved configs |
| `GET /configs/{id}` | — | `ConfigPayload` (`{ id, yaml, descriptors }`) | 404 if missing |
| `PUT /configs/{id}` | `{ yaml }` | `ConfigPayload` | 409 if the YAML's `adapter.id` ≠ path id (no rename) |
| `POST /configs/match` | `{ data, format, source? }` | `ConfigMatch[]` | parses records, then for each saved config checks source equality and per-record `can_handle`, returning matched/total counts; sorted applicable-first |
| `POST /transform` | `TransformRequest` | `TransformResponse` | the pipeline; see below |
| `POST /suggest-config-fix` | `{ yaml, diagnostics, sample_record, description? }` | `{ yaml }` | LLM repair; not saved |
| `POST /edit-config` | `{ yaml, instruction, sample_data?, source? }` | `{ yaml }` | NL edit; not saved |
| `GET /terminology/search` | `?system=&q=&max=` | `TerminologySearchResult[]` | OMOPHub proxy; `system ∈ {loinc,ucum,snomed,rxnorm,icd10,cpt}` |
| `POST /suggest-concepts` | `{ slots }` | `{ suggestions, no_matches, errors }` | LLM + tool-calling, with the anti-hallucination guard |

**`TransformRequest`** = `{ data, yaml, source?, device?, format ("json"/"csv"),
concept_mappings?: {slotKey: Coding}, concept_scan_only?: bool }`. The handler first
validates the YAML parses to a mapping and that `ConfigAdapter.from_dict` accepts it
(else 400). If `concept_scan_only`, it runs `scan_concepts` and returns only
`concept_slots` + `adapter_diagnostics`. Otherwise it runs `run_pipeline` and returns
**`TransformResponse`** = `{ events: [event.to_dict()], stats, bundle?, omop_cdm?,
concept_slots, adapter_diagnostics }`. Before returning it flattens parts of `stats`
into dotted keys (`fhir.resource_count`, `fhir.size_bytes`,
`omop.measurement_count`, `omop.observation_count`, `omop.unmapped_count`,
`mapper.slot_count`, `mapper.unbound_count`) and lifts the `bundle` and `omop_cdm`
out of the stats dict. A `ValueError` from any stage becomes HTTP 400.

---

## 18. Config store & matching

`backend/api/configs_store.py` persists configs as YAML files in
`backend/configs/existing_configs/`. `save_new_config` parses+validates via
`ConfigAdapter.from_dict`, slugs the `adapter.id` to a filename-safe form
(`[a-zA-Z0-9_-]`), auto-increments a suffix on collision (`config-2.yaml`, …), and
writes both `{id}.yaml` and a sidecar `{id}.descriptors.json` holding the uploaded
schema/spec files (invisible to `*.yaml` listings). `load_parsed_configs` returns
`(id, parsed_dict)` pairs for all configs (skipping unparseable ones);
`list_configs` derives a `ConfigSummary` (`id, version, description, source,
record_filters`) from each. `get_config`/`update_config` round-trip the YAML
(`update` forbids renaming — 409 on id mismatch). `ConfigStoreError` carries a
`status_code` (400/404/409). The saved configs double as the curated corpus and the
`/configs/match` candidate set, so the system improves as users save good configs.

---

## 19. Frontend & UX workflow

A Next.js single-page app (`frontend/`, static export, client-only) with a Monaco
editor. `lib/api.ts` is a thin typed client over every endpoint, reading
`NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`); the FHIR dashboard
reads `NEXT_PUBLIC_FHIR_BASE_URL` and talks to HAPI directly.

`app/page.tsx` is a stage machine: **Connector → Adapter → (Cleaning · Validation ·
Qualification) → Results**, with a **FHIR Server** overlay. The end-to-end flow:

1. **Ingest (ConnectorPanel).** Drop/paste JSON or CSV, or pick a bundled sample;
   the source name is captured; large pastes are debounced (≈350 ms).
2. **Config (AdapterPanel).** `/api/configs/match` ranks applicable saved configs.
   The user picks one, or **generates** a new one with the LLM (sample + description
   + hints + optional descriptor files), or **edits** an existing one — visually
   (match/defaults/emit tabs) or in the **Monaco YAML editor**. "Edit with AI" calls
   `/api/edit-config` and shows the result in a **`YamlDiffEditor`** (side-by-side
   Monaco diff) before applying and saving.
3. **Transform.** `handleRun` splits very large datasets into batches (≈50k records)
   with an `AbortController`, calling `/api/transform` per batch and merging the
   responses. For large inputs a **concept-scan** phase
   (`concept_scan_only=true` on a ~100-record sample) discovers slots so the user can
   bind concepts before the full run.
4. **Concept binding (ConceptsPanel).** Slots are grouped by kind; code slots offer
   a LOINC↔SNOMED toggle, unit slots search UCUM, category slots offer the fixed
   FHIR category set — all via `/api/terminology/search`. "Suggest all" calls
   `/api/suggest-concepts` (LLM). Picks are stored in session and re-sent on each
   transform.
5. **Inspect (ResultsPanel).** Tabs: **Events** (paginated table + per-event drawer
   showing all flags/extensions), **Concepts**, **FHIR Bundle** (resource counts,
   coding tally, pretty-print, copy/download, **Export to HAPI** via a transaction
   POST), **OMOP CDM** (per-table preview + CSV/JSON download), **Debug** (the
   `AdapterDiagnostics`: per-rule stats, skip reasons, predicate failures, and a
   **"Suggest Fix"** button calling `/api/suggest-config-fix`, previewed in the diff
   editor).
6. **FHIR Server dashboard.** Connects straight to HAPI: live resource counts, a
   patient browser, an observation table, and raw-resource JSON views — demonstrating
   that the exported bundles are genuine, queryable FHIR.

Monaco is dynamically imported (`ssr: false`) to avoid hydration issues.

---

## 20. Deployment & configuration

- **Docker:** `docker compose up -d` brings up `api` (:8000), `frontend` (:3000),
  `hapi-fhir` (:8080, Postgres-backed via `hapi-db` + the `hapi-pgdata` volume).
  Frontend build args bake `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_FHIR_BASE_URL`.
- **Local backend:** `pip install -e .`, set `.env`, `uvicorn api.main:app --reload
  --port 8000`. F5 in VS Code launches the same under debugpy.
- **Local frontend:** `npm install && npm run dev` (`:3000`).
- **Backend env vars:** `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GOOGLE_API_KEY`
  (matching `LLM_PROVIDER`, default `anthropic`); `LLM_MODEL` (default
  `claude-opus-4-7`); `OMOPHUB_API_KEY` (required for terminology + OMOP routing);
  `ALLOWED_ORIGIN` (CORS, default `http://localhost:3000`).
- **Frontend env vars:** `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_FHIR_BASE_URL`.

---

## 21. Consolidated design decisions & considerations

- **Progressive, observable harmonization.** The explicit `Stage` ladder + the
  append-only `quality.flags` audit trail are the thesis's core artifact: every
  transformation is inspectable and attributable, not a black box.
- **Tag, don't drop.** Validation never filters; failures are flagged and the
  qualifier marks plausibility so consumers choose their own cut-off. This preserves
  chain-of-custody. The *only* deliberate omission is OMOP excluding
  `plausibility="exclude"` events, justified by analytics contamination.
- **Statelessness + determinism.** No DB; everything in-process per request. To
  keep outputs reproducible and idempotent without a registry, identity is derived by
  hashing: FHIR UUID5 from stable seeds, OMOP `person_id` from SHA-256, custom OMOP
  concepts from `hash(system|code)`.
- **A declarative DSL over per-source code.** One YAML fully specifies the adapter
  *and* the downstream stage configuration, executed by a single generic engine.
  This is what makes LLM authoring viable: the model emits data, not code.
- **The LLM emits configs, humans review.** Generation/repair/edit are all
  previewable and editable; concept suggestion is tool-grounded and
  hallucination-guarded. The match block is forced to be strict so failures are
  visible ("no config matches") rather than silently wrong.
- **Payload triage philosophy.** The explicit value/component/extension decision
  (with the "value is never also a component" hard rule, enforced at load time)
  ensures no analytically-relevant field is lost and none is duplicated across the
  FHIR/OMOP projections.
- **Two projections, one model.** FHIR (exchange, tolerant codings, nested
  components, surveys as QuestionnaireResponse) and OMOP (analytics, mandatory
  concept_ids, flattened components, surveys as observation rows) are read-only
  parallel outputs of the same mapped events.
- **Data-quality grounding.** The `Quality` object and the qualifier deliberately
  follow Kahn et al. 2016 (Conformance / Completeness / Plausibility); the Hampel
  identifier (median ± 3.5·MAD, min group 5) is a robust, defensible outlier test;
  physiological ranges (e.g. HR 30–220) align with literature such as Tanaka et al.
  2001.

---

## 22. Known limitations & future work

- **No persistence layer.** Cross-request outlier baselines, longitudinal dedup, and
  global row IDs are out of scope; the qualifier is single-request.
- **No formal test suite.** Verification has been ad-hoc smoke runs against
  `sample_data/`.
- **`_quality_override` plumbing** through `event.extensions` is a deliberate hack to
  keep the validator stateless.
- **OMOP coverage depends on OMOPHub.** Consumer-health metrics outside the major
  vocabularies (Active Zone Minutes, game scores, app-specific metrics) remain at
  `concept_id=0` (or a custom 2-billion concept); without `OMOPHUB_API_KEY`, OMOP
  routing degrades to `concept_id=0`.
- **FHIR CodeableConcepts are text-only** unless the user binds codes via the mapper;
  fully automated, review-free terminology binding is not yet implemented.

---

## 23. File / module map (for citing paths)

| What | Where |
|---|---|
| FastAPI app + CORS | `backend/api/main.py` |
| HTTP routes | `backend/api/routes.py` |
| Pydantic schemas | `backend/api/models.py` |
| LLM client + prompts (DSL spec) | `backend/api/llm/`, `backend/api/prompts.py` |
| LLM tool definitions | `backend/api/llm/tools.py` |
| Terminology client (OMOPHub) | `backend/api/terminology.py` |
| Config CRUD | `backend/api/configs_store.py` |
| Pipeline orchestrator | `backend/pipeline/__init__.py` |
| Connector | `backend/pipeline/connector/` |
| Adapter engine | `backend/pipeline/adapter/config_adapter.py` |
| Adapter diagnostics | `backend/pipeline/adapter/diagnostics.py` |
| Cleaning heuristics | `backend/pipeline/cleaner/` |
| Validators | `backend/pipeline/validator/` |
| Qualifier | `backend/pipeline/qualifier/` |
| Mapper (concept slots) | `backend/pipeline/mapper/` |
| FHIR R4 builder | `backend/pipeline/fhir/` |
| OMOP CDM builder | `backend/pipeline/omop/` |
| Canonical event model | `backend/domain/models.py` |
| Quality rules loader / data | `backend/domain/rules.py` · `backend/configs/quality_rules.yaml` |
| Adapter examples (= LLM few-shot) | `backend/configs/examples/` |
| User/LLM-saved configs | `backend/configs/existing_configs/` |
| Single-page UI | `frontend/app/page.tsx` + `frontend/components/` |
| API client | `frontend/lib/api.ts` |
| Companion design doc | `docs/canonical-to-fhir-and-omop.md` |

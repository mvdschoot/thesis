# DSL reference

The complete grammar of an adapter config, block by block. For the value-binding mini-language
referenced throughout (`{ path: ... }`, transforms, templates, lookups), see
[Value specs](value-specs.md).

---

## `adapter` (required)

Identity metadata. Propagated onto every event's `provenance.adapter` / `adapter_version`.

```yaml
adapter:
  id: "withings-body-scale-v1"   # unique id for this config
  version: "1.0.0"               # your version string
  description: "Withings Body+ scale measurements"
```

| Key | Required | Notes |
|---|---|---|
| `id` | Yes | Becomes `provenance.adapter`. |
| `version` | Yes | Becomes `provenance.adapter_version`. |
| `description` | Recommended | Free text; no validation. |

---

## `match` (required)

A **cheap routing check** that decides whether this config handles a given record. It is *not* a
schema validator.

```yaml
match:
  source: "withings"            # MUST equal the request's source name (string equality)
  record:                       # optional list of predicates, implicitly AND-ed
    - { field: "userId", exists: true }
    - { field: "measurementValue", exists: true }
```

- **`source`** (required) — must exactly equal the `source` sent with the request.
- **`record`** (optional) — a list of predicate entries. Every entry must pass (logical AND).

### Predicate verbs

Each entry has a `field` (a [dot-path](value-specs.md#paths), supports `[index]`) and one or more
verbs, AND-ed within the entry:

| Verb | Meaning |
|---|---|
| `equals: X` | exact equality |
| `in: [A, B, C]` | value is a member of the list |
| `exists: true` | value is present / not null |
| `exists: false` | value is null or missing |
| `type: "<t>"` | one of `object`, `array`, `string`, `number`, `integer`, `boolean`, `null` |
| `non_empty: true` | arrays / strings / objects must have length > 0 |

!!! warning "Keep the match block SHORT and loose"
    At most 2–3 predicates, all on **top-level** fields. Assert `exists: true` on one or two
    characteristic fields (the subject-id field, the timestamp field, the root array the rules
    iterate). If the source mixes record kinds and has a top-level discriminator (`dataType`,
    `recordKind`), pin it with `equals`/`in`. **Do not** enumerate every field the rules read or
    match on deeply nested paths — an over-strict match block rejects the very data it was built
    for. Bad records that slip through are tagged downstream; a non-matching config produces
    nothing.

The same predicate shape is reused by the per-rule [`when:`](#when-optional) gate.

---

## `defaults` (block optional — `subject_id` mandatory)

Values applied to every emitted event.

```yaml
defaults:
  subject_id: { path: "userId" }            # MANDATORY (see below)
  context:
    source: "withings"                       # defaults to match.source
    modality: "scale"                        # see allowed values below
    device: null                             # defaults to the request's device
    source_measurement_type: { path: "measurementType.typeDescription" }
  stage: "structured"                        # default: "structured"
  source_record_id:
    template: "withings:{userId}:{measurementType.typeValue}:{measurementDateTime}"
```

### `subject_id` (mandatory)

Every event must have a non-null `subject_id`. There are two cases:

=== "The source has a person identifier"

    Bind it directly. This is the common case and needs **no** quality flag.

    ```yaml
    defaults:
      subject_id: { path: "userId" }
    ```

=== "The source has no person identifier"

    Synthesize one as `"<source>:<record_id>"`, falling back to the record index, **and** add a
    `SYNTHETIC_SUBJECT_ID` flag to every emit rule (see [Quality & flags](quality-and-flags.md)).

    ```yaml
    defaults:
      subject_id: { template: "questionnaire:{@record_index}" }
    ```

!!! note "The flag rule is mechanical"
    Look only at the `subject_id` spec: a spec containing `path:` binds a real field → **no
    flag**. A `template:` spec with no `path:` (embedding the source name and/or
    `{@record_index}`) → **add the flag**. A `template:` that merely reformats one real field is
    not synthetic — prefer `path:` there.

### `context`

| Key | Default if omitted |
|---|---|
| `source` | `match.source` |
| `modality` | `"unknown"` |
| `device` | the request's `device` metadata |
| `source_measurement_type` | `null` |

**`modality`** must resolve to one of: `wearable`, `scale`, `survey`, `sensor`, `app`, `game`,
`vr`, `unknown` (an unrecognized value falls back to `unknown`). The OMOP stage derives the
`*_type_concept_id` from this value.

### `stage`

The initial stage stamped on events. Default `"structured"`; you should rarely change it.

### `source_record_id`

A stable identifier for the originating record. If omitted, the engine builds one from
`source:userId:measurementType:measurementDateTime`. Prefer setting it explicitly with a
`template:` so it is meaningful for your source.

---

## `emit` (required)

A list of rules. Each rule produces **0..n** events per input record.

```yaml
emit:
  - id: "body-measurement"
    description: "One scalar body measurement"
    type: "measurement"
    category: "weight"
    granularity: "instant"
    when: ...            # optional gate
    parent: ...          # optional link to another rule
    iterate: ...         # optional array fan-out
    iterate_object: ...  # optional object-key fan-out
    timestamp: { start, end?, duration_seconds? }
    payload: { value?, raw_value?, unit?, label?, components? }
    extensions: { ... }
    quality: { flags: [...] }
    quality_overrides: { ... }
```

### `id` and `description`

`id` is required and must be unique within the config — it is used in diagnostics and as the
`parent:` target. `description` is free text.

### `type` (required)

One of:

| `type` | Meaning | FHIR projection |
|---|---|---|
| `measurement` | quantitative data (HR, weight, steps) | `Observation` |
| `observation` | narrative / categorical | `Observation` |
| `survey` | questionnaire response | `QuestionnaireResponse` |
| `event` | a discrete occurrence | `Observation` |
| `summary` | aggregated data | `Observation` |
| `session` | a multi-item session (workout, game round) | `Observation` |

`type` may itself be a value-spec when the kind is data-dependent.

### `category` (required)

A canonical category name, looked up in the global
[`quality_rules.yaml`](quality-and-flags.md#the-global-rules) for validation and qualification.
Often a static string (`"heart-rate"`), but may be a value-spec — e.g. a `lookup` keyed on the
record's metric type.

### `granularity`

One of `instant`, `interval`, `daily`, `session`, `unknown` (default `unknown`). May be a
value-spec.

### `when` (optional)

A predicate — or a list of predicates, AND-ed — that gates whether this rule fires for a record.
Same shape and verbs as [`match.record`](#predicate-verbs). This is the canonical way to handle a
source that interleaves multiple record kinds in one stream: write one rule per kind and gate each.

```yaml
when:
  - { field: "measurementType", equals: "steps" }
```

Records matching no rule emit nothing (surfaced as a `when_not_met` diagnostic).

### `parent` (optional)

Another rule's `id`. Events from this rule are linked to the **first** event of the parent rule
via `provenance.parent_event_id`. If the parent rule produced no events for the record, this rule
also produces none (`parent_rule_empty` diagnostic).

### `iterate` (optional) — array fan-out

Produces one event per element of an array. Inside the rule, `@item` references the current
element and `@event` reaches back to the whole record.

```yaml
iterate: "measurementValue.activities-steps-intraday.dataset"
payload:
  value: { path: "@item.value" }
timestamp:
  start:
    date_from: { path: "measurementDateTime" }   # event-level field
    time_from: { path: "@item.time" }             # per-element field
```

`iterate` is normally a dot-path string, but may also be a value-spec (e.g. a `lookup` that picks
the array per record kind). If the path is missing / not a list / empty, the rule emits nothing
(diagnostics: `iterate_path_none`, `iterate_not_list`, `iterate_empty`).

### `iterate_object` (optional) — object-key fan-out

Expands an object's keys into one event per key. Ideal for wide questionnaire / survey CSVs.

```yaml
iterate_object:
  source: "."           # path to the source dict; "." or omit = the whole record
  all_keys: true        # auto-iterate every key
  exclude: [Timestamp]  # skip non-question columns
```

Two modes:

- **`entries:`** — an explicit list of `{ key, label }` to iterate.
- **`all_keys: true`** — iterate every key, optionally minus `exclude:`. Preferred for surveys
  with many columns.

Each iteration produces an `@item` with fields `key`, `name` (= key), `question` (= key),
`label`, and `value`. Reference them as `@item.value`, `@item.label`, etc.

```yaml
iterate_object:
  entries:
    - { key: "q1", label: "Do you feel happy?" }
    - { key: "q2", label: "Do you exercise regularly?" }
```

### `timestamp` (required for a usable event)

```yaml
timestamp:
  start: { path: "measurementDateTime", transform: "iso_millis" }  # required
  end:   { path: "endedAt", transform: "iso_millis" }              # optional, for intervals
  duration_seconds: { path: "durationSec" }                        # optional
```

`start` is the canonical event timestamp. See
[Value specs → timestamps](value-specs.md#timestamps) for choosing between `iso_millis`,
`parse_timestamp`, and composite `date_from`/`time_from`. If the source has no per-record
timestamp at all, set a literal ISO string and add a `SYNTHETIC_TIMESTAMP`
[quality flag](quality-and-flags.md).

### `payload` (the field-triage core)

```yaml
payload:
  value:     { path: "measurementValue" }   # the SINGLE headline data point
  raw_value: { path: "measurementValue" }   # original unprocessed value
  unit:      "kg"
  label:     { path: "measurementType.typeDescription" }
  components:                                # every OTHER analytically relevant field
    - { name: "systolic",  value: { path: "sys" }, unit: "mmHg" }
    - { name: "diastolic", value: { path: "dia" }, unit: "mmHg" }
```

Assign **every meaningful field of the record to exactly one** of `value`, `components`, or
`extensions`:

| Role | Goes to | Decision test |
|---|---|---|
| The headline measurement / primary entity of the row | `payload.value` | "Is this *the point* of the row?" Pick exactly one. Set `null` only for a genuinely composite concept (e.g. blood pressure). |
| Any other field an analyst would plot, aggregate, or filter on | `payload.components[]` | "Would an analyst compute on it?" One entry per field: `{ name, value, unit? }`. May coexist with a non-null `value`. |
| Opaque IDs, audit timestamps, attribution flags, bookkeeping | `extensions` | "Is it just provenance / bookkeeping?" Prefix keys with the source name. |

!!! danger "A value is never also a component"
    A field used as `payload.value` (or `raw_value`) **must not** also appear as a component. A
    component whose `value` spec equals `payload.value`'s spec is **stripped at load time** (and
    reported as a `redundant_component_dropped` diagnostic), because it would duplicate the data
    in both `value[x]` and `component[]` of the FHIR Observation.

### `extensions` (optional)

A free-form `{ key: <value-spec> }` map for metadata only. Prefix keys with the source name:

```yaml
extensions:
  withings.attrib:          { path: "attrib" }
  withings.createdDateTime: { path: "createdDateTime" }
```

### `quality` and `quality_overrides` (optional)

Attach quality flags and override per-category rules for this rule. Covered fully in
[Quality & flags](quality-and-flags.md).

---

## `clean` (optional)

Compose the cleaning heuristic chain and tune each heuristic. Omit for the default chain.

```yaml
clean:
  heuristics:
    - whitespace
    - name: timestamp_normalizer
      accept_formats: ["%m/%d/%Y %I:%M:%S %p"]
    - type_coercer
    - name: unit_inferrer
      mappings: { "withings|body-water": "kg" }
```

Each entry is either a name string or `{ name, ...params }`. The list order is the execution
order; listing a subset skips the others. Closed enum:

| Heuristic | Params | Does |
|---|---|---|
| `whitespace` | — | strips leading/trailing whitespace on string fields |
| `timestamp_normalizer` | `accept_formats: [<strptime>, ...]` | normalizes timestamps to ISO 8601 UTC (after the built-in ISO / date-only handling) |
| `type_coercer` | — | coerces numeric strings on `payload.value` and components |
| `unit_inferrer` | `mappings: { "<source>\|<category>": "<unit>" }` | fills `payload.unit` when the adapter left it null |

**Default chain when `clean` is omitted:** `whitespace → timestamp_normalizer → type_coercer →
unit_inferrer`, each with defaults.

---

## `validate` (optional)

Choose which validators run and overlay per-category rules on top of the global
`quality_rules.yaml`.

```yaml
validate:
  enabled: [required_fields, timestamp_window, payload_shape, unit_whitelist, range]
  timestamp_window: { min: "2010-01-01", max: "now+1d" }
  categories:
    heart-rate:
      unit_whitelist: [bpm]
      range: { min: 25, max: 230, on_violation: { severity: warning, code: HR_OUT_OF_RANGE } }
```

| Key | Notes |
|---|---|
| `enabled` | subset of `[required_fields, timestamp_window, payload_shape, unit_whitelist, range]`. Canonical order is preserved regardless of how you list it. Omit to run all five. |
| `timestamp_window: { min, max }` | overrides the global window. Accepts ISO strings or `now+Xd` / `now-Xh`. |
| `categories.<cat>` | per-category overlay; each key is a **shallow replace** of the global rule. |

Per-category keys:

- `expected_fields: [<dotted-paths>]` — fields the completeness check looks for.
- `unit_whitelist: [<units>]` — allowed values of `payload.unit`; otherwise emits
  `UNIT_NOT_IN_WHITELIST` (warning).
- `range: { min, max, on_violation: { severity, code } }` — numeric range on `payload.value`.
  `severity ∈ {info, warning, error}`; `code` is the flag emitted on violation.

Only add a `categories` override when the source genuinely deviates from the global rule.

---

## `qualify` (optional)

Choose which cross-event checks run and tune them.

```yaml
qualify:
  enabled: [completeness, duplicates, outliers, conformance, plausibility]
  outliers:    { hampel_k: 3.5, min_group_size: 5 }
  duplicates:  { fields: [subject_id, category, timestamp, payload.value], value_round_digits: 3 }
  plausibility: { warning_count_for_review: 1 }
  completeness: { expected_fields: { heart-rate: [subject_id, timestamp, payload.value, payload.unit] } }
```

| Key | Notes |
|---|---|
| `enabled` | subset of `[completeness, duplicates, outliers, conformance, plausibility]`. Omit to run all five. |
| `outliers` | Hampel test (median ± `hampel_k`·MAD) per `(subject_id, category)`. Lower `hampel_k` flags more. `min_group_size` is the floor below which the test is skipped. |
| `duplicates` | `fields` is the fingerprint (any dotted path); `value_round_digits` rounds numeric values before comparison. |
| `plausibility` | `warning_count_for_review` — number of WARNING flags after which `quality.plausibility` becomes `"review"`. Any ERROR forces `"exclude"`. |
| `completeness` | per-category `expected_fields` override for the completeness ratio. |

!!! warning "Don't lower `min_group_size` without justification"
    Below ~5 events per group, the MAD collapses toward 0 and the Hampel test flags everything.

---

## `fhir` (optional — omit by default)

Tunes the FHIR R4 bundle. **Omit entirely unless you need non-default output.**

```yaml
fhir:
  enabled: true                 # default true; false returns no bundle
  bundle_type: transaction      # or "collection"; default "transaction"
  include: [Patient, Observation, Device, Provenance, Questionnaire]
```

| Key | Default | Notes |
|---|---|---|
| `enabled` | `true` | `false` skips the stage / returns no bundle. |
| `bundle_type` | `transaction` | `transaction` adds `entry.request.method/url` (POST-able); `collection` omits it. |
| `include` | `[Patient, Observation, Questionnaire]` | subset of `[Patient, Observation, Device, Provenance, Questionnaire]`. Add `Device` when `context.device` is meaningful; add `Provenance` for an explicit audit trail. |

See [Engine → FHIR projection](../engine/fhir.md) for the hardcoded mapping rules (status,
value types, references) that are *not* configurable here.

---

## `omop` (optional — omit by default)

Tunes the OMOP CDM v5.4 output. **Omit entirely unless you need non-default output.**

```yaml
omop:
  enabled: true
  include: [person, measurement, observation, device_exposure, observation_period]
```

| Key | Default | Notes |
|---|---|---|
| `enabled` | `true` | `false` returns no OMOP tables. |
| `include` | all five | subset of `[person, measurement, observation, device_exposure, observation_period]`. |

See [Engine → OMOP projection](../engine/omop.md) for table routing and the concept-resolution
behavior that is *not* configurable here.

---

## Defaults & omission rule

Every block, nested key, and parameter is optional except the required core (`adapter`, `match`,
`emit`, and `defaults.subject_id`). Omitted means current default behavior. Prefer the smallest
config that works; if you cannot infer a parameter from the data, omit it rather than invent a
threshold.

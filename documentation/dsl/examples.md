# Examples

Three complete, working configs drawn from the project's own corpus, annotated. Copy one that
resembles your source and adapt it. All three live under `backend/configs/` and double as the
few-shot corpus for the LLM config generator.

---

## 1. One rule, many metric kinds (Withings scale, JSON)

Each record is one scalar body measurement. A single rule derives both `category` and `unit` from
the metric-type field via `lookup`, and attaches conditional quality flags from an `attrib` field.

```yaml
adapter:
  id: "withings-body-scale-v1"
  version: "1.0.0"
  description: "Withings Body+ scale measurements (Weight, Height, Fat Ratio, ...)"

match:
  source: "withings"
  record:                                # loose: two existence checks route the record
    - { field: "userId", exists: true }
    - { field: "measurementValue", exists: true }

defaults:
  subject_id: { path: "userId" }         # real identifier -> no synthetic flag
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
    category:                            # category depends on the metric kind
      lookup:
        key: { path: "measurementType.typeDescription" }
        map:
          "Weight": "weight"
          "Height": "height"
          "Fat Ratio": "body-fat-ratio"
          "Heart Rate": "heart-rate"
          "Systolic Blood Pressure": "blood-pressure-systolic"
        default: "unknown"
    timestamp:
      start: { path: "measurementDateTime", transform: "iso_millis" }
    payload:
      value:     { path: "measurementValue" }
      raw_value: { path: "measurementValue" }
      unit:                              # unit derived from the same field
        lookup:
          key: { path: "measurementType.typeDescription" }
          map: { "Weight": "kg", "Height": "m", "Heart Rate": "bpm" }
          default: null
      label: { path: "measurementType.typeDescription" }
    extensions:
      withings.typeValue: { path: "measurementType.typeValue" }
      withings.attrib:    { path: "attrib" }
    quality:
      flags:
        - condition: { path: "attrib", equals: 2 }
          code: "MANUAL_ENTRY"
          severity: "info"
          stage: "structured"
          message: "Measurement entered manually by the user (attrib=2)"

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
  outliers:    { hampel_k: 3.5, min_group_size: 5 }
  duplicates:  { fields: [subject_id, category, timestamp, payload.value], value_round_digits: 3 }
  plausibility: { warning_count_for_review: 1 }

# No fhir:/omop: blocks — omission enables both with all defaults.
```

**Why it's shaped this way:** one physical row = one measurement, so one rule suffices; the
`lookup` pattern keeps category/unit data-driven; `attrib` is bookkeeping → `extensions`, but its
*meaning* (manual entry, ambiguous subject) is surfaced as conditional flags.

---

## 2. Mixed record kinds + intraday fan-out (Fitbit, JSON)

One JSON stream interleaves different `measurementType`s. Each rule is gated with `when:` so it
only fires for its own kind. The intraday rule uses `iterate` to emit one event per time slice,
combining a per-element time with the event-level date.

```yaml
adapter:
  id: fitbit-multi-type-json
  version: 1.0.0
  description: Fitbit JSON where each element is a different kind, discriminated by measurementType.

match:
  source: fitbit
  record:
    - { field: userId, exists: true }
    - { field: measurementType, exists: true }

defaults:
  subject_id: { path: userId }
  context:
    source: fitbit
    modality: wearable
    device: null
    source_measurement_type: { path: measurementType }
  stage: structured
  source_record_id:
    template: "fitbit:{userId}:{measurementType}:{measurementDateTime}"

emit:
  - id: daily-steps                       # only fires for steps records
    type: measurement
    category: steps
    granularity: daily
    when: { field: measurementType, equals: steps }
    timestamp:
      start: { path: measurementValue.activities-steps[0].dateTime, parse_timestamp: '%Y-%m-%d' }
    payload:
      value: { path: measurementValue.activities-steps[0].value }
      unit: steps
      label: daily steps

  - id: intraday-steps                    # one event per dataset slice
    type: measurement
    category: steps-intraday
    granularity: interval
    when: { field: measurementType, equals: steps }
    iterate: measurementValue.activities-steps-intraday.dataset
    timestamp:
      start:
        date_from: { path: measurementDateTime }   # event-level
        time_from: { path: '@item.time' }           # per-element
    payload:
      value: { path: '@item.value' }
      unit: steps
      label: intraday steps

validate:
  enabled: [required_fields, timestamp_window, payload_shape, unit_whitelist, range]
  categories:
    steps:          { unit_whitelist: [steps] }
    steps-intraday: { unit_whitelist: [steps] }
```

**Why it's shaped this way:** `when:` is the canonical way to handle heterogeneous streams —
each rule stays inert (emits zero events, not null ones) for the wrong kind. `iterate` fans an
intraday array into one event per slice. The per-category `unit_whitelist` overrides exist because
`steps` uses the unit `steps` here rather than the global `count`.

---

## 3. Wide survey CSV with no person id (questionnaire)

A Google-Form CSV: one column per question, no person identifier. `iterate_object` with
`all_keys: true` fans every question column into one survey event; `subject_id` is synthesized
from the row index and flagged accordingly.

```yaml
adapter:
  id: questionnaire
  version: 1.1.0
  description: Student well-being questionnaire CSV. One survey event per (respondent, question).

match:
  source: questionnaire
  record:
    - { field: Timestamp, exists: true }
    - { field: "32. Gender", exists: true }

defaults:
  subject_id: { template: "questionnaire:{@record_index}" }   # synthesized -> needs the flag
  context:
    source: questionnaire
    modality: survey
    device: null
    source_measurement_type: student well-being questionnaire
  stage: structured
  source_record_id: { template: "questionnaire:{@record_index}" }

emit:
  - id: student-wellbeing-item
    description: One survey event per answered question.
    type: survey
    category: student-wellbeing
    granularity: instant
    timestamp:
      start: { path: Timestamp, parse_timestamp: '%m/%d/%Y %H:%M:%S' }
    iterate_object:
      source: .                # the whole row
      all_keys: true           # one event per column...
      exclude: [Timestamp]     # ...except the timestamp column
    payload:
      value:     { path: '@item.value' }   # the answer is the headline value
      raw_value: { path: '@item.value' }
      label:     { path: '@item.label' }   # the question text is the label
    quality:
      flags:
        - code: SYNTHETIC_SUBJECT_ID
          severity: info
          stage: structured
          message: "No person identifier in source data; subject_id synthesized as questionnaire:{@record_index}"

clean:
  heuristics:
    - whitespace
    - { name: timestamp_normalizer, accept_formats: ['%m/%d/%Y %H:%M:%S'] }
    - type_coercer
    - unit_inferrer

validate:
  enabled: [required_fields, timestamp_window, payload_shape, unit_whitelist, range]
  timestamp_window: { min: '2024-01-01', max: now+1d }

qualify:
  enabled: [completeness, duplicates, outliers, conformance, plausibility]
  duplicates: { fields: [subject_id, category, timestamp, payload.label], value_round_digits: 3 }
  plausibility: { warning_count_for_review: 1 }

fhir:
  include: [Observation, Patient, Provenance, Questionnaire]   # explicit: add Provenance
```

**Why it's shaped this way:** `iterate_object` + `all_keys` avoids listing dozens of question
columns; the answer/question split maps cleanly to `value`/`label`; the missing person identifier
forces a synthesized `subject_id` plus the `SYNTHETIC_SUBJECT_ID` flag. The duplicate fingerprint
uses `payload.label` (the question) rather than `payload.value`, since many answers repeat.

---

See the [Cookbook](cookbook.md) for smaller task-focused snippets, and
[Diagnostics](diagnostics.md) if a config emits nothing.

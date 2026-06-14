# Cookbook

Task-oriented recipes. Each is a snippet you drop into the relevant block of a config. For the
full grammar see the [Reference](reference.md); for value-binding details see
[Value specs](value-specs.md).

## Bind a person identifier

```yaml
defaults:
  subject_id: { path: "userId" }    # any real id field; no quality flag needed
```

## Synthesize a subject id when none exists

```yaml
defaults:
  subject_id: { template: "supermarket:{sessionId}" }   # or "{...}:{@record_index}"
emit:
  - id: ...
    quality:
      flags:
        - { code: SYNTHETIC_SUBJECT_ID, severity: info, stage: structured,
            message: "No person identifier; subject_id synthesized" }
```

## Parse a non-ISO timestamp

```yaml
timestamp:
  start: { path: "createdAt", parse_timestamp: "%m/%d/%Y %I:%M:%S %p" }   # "3/12/2016 2:00:00 AM"
```

## Combine a split date + time (CSV)

```yaml
# Composite form
timestamp:
  start:
    date_from: { path: "ActivityDate" }
    time_from: { path: "ActivityTime" }
```

```yaml
# Template + parse form (when the parts aren't ready-made ISO)
timestamp:
  start:
    template: "{ActivityDate} {ActivityTime}"
    parse_timestamp: "%m/%d/%Y %I:%M:%S %p"
```

## Synthesize a timestamp when the source has none

```yaml
timestamp:
  start: "2025-01-01T00:00:00.000Z"      # literal ISO string
quality:
  flags:
    - { code: SYNTHETIC_TIMESTAMP, severity: info, stage: structured,
        message: "Source has no timestamp; start synthesized" }
```

## Derive category and unit from one field

```yaml
category:
  lookup:
    key: { path: "metricType" }
    map: { "HR": "heart-rate", "WT": "weight" }
    default: "unknown"
payload:
  unit:
    lookup:
      key: { path: "metricType" }
      map: { "HR": "bpm", "WT": "kg" }
      default: null
```

## Handle a stream that mixes record kinds

Write one rule per kind, each gated with `when:`.

```yaml
emit:
  - id: steps
    when: { field: "type", equals: "steps" }
    category: steps
    # ...
  - id: calories
    when: { field: "type", equals: "calories" }
    category: calories
    # ...
```

## Fan out an array into one event per element

```yaml
iterate: "readings"           # dot-path to the array
payload:
  value: { path: "@item.value" }
timestamp:
  start: { path: "@item.ts", transform: "iso_millis" }
extensions:
  batchId: { path: "@event.batchId" }   # reach back to the record
```

## Fan out wide survey columns

```yaml
iterate_object:
  source: .
  all_keys: true
  exclude: [Timestamp, RespondentId]
payload:
  value: { path: "@item.value" }   # the answer
  label: { path: "@item.label" }   # the question (= column name)
```

## A composite measurement (blood pressure)

`value` is null because there is no single headline; the two readings are components.

```yaml
payload:
  value: null
  components:
    - { name: "systolic",  value: { path: "sys" }, unit: "mmHg" }
    - { name: "diastolic", value: { path: "dia" }, unit: "mmHg" }
```

## Keep descriptive fields without polluting the value

```yaml
payload:
  value: { path: "exerciseId" }      # the headline
  components:                         # analytically relevant context
    - { name: "week", value: { path: "week" } }
    - { name: "day",  value: { path: "day" } }
extensions:
  uploadId: { path: "uploadId" }      # pure bookkeeping
```

## Loosen a range or unit for one source

```yaml
validate:
  categories:
    heart-rate:
      unit_whitelist: [bpm, "beats/min"]
      range: { min: 30, max: 220, on_violation: { severity: warning, code: HR_OUT_OF_RANGE } }
```

## Add a Provenance or Device resource to the FHIR bundle

```yaml
fhir:
  include: [Patient, Observation, Device, Provenance]
```

## Disable an OMOP table

```yaml
omop:
  include: [person, measurement, observation_period]   # drops observation + device_exposure
```

## Tune duplicate detection

```yaml
qualify:
  duplicates:
    fields: [subject_id, category, timestamp, payload.label]   # fingerprint over the question, not the answer
    value_round_digits: 3
```

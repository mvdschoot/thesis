# DSL overview

An adapter config is a single YAML document. It tells the generic engine how to turn records
from one data source into canonical events — and, optionally, how the downstream cleaning,
validation, qualification, FHIR, and OMOP stages should behave for that source.

No source-specific Python is written. The same engine interprets every config.

## Anatomy of a config

```yaml
adapter:   { id, version, description }   # (1) who this config is
match:     { source, record? }            # (2) which records it handles
defaults:  { subject_id, context, ... }   # (3) values applied to every event
emit:      [ { rule }, { rule }, ... ]    # (4) how to produce events from a record

clean:     { ... }   # (optional) tune the cleaning heuristics
validate:  { ... }   # (optional) tune the validators
qualify:   { ... }   # (optional) tune the cross-event quality checks
fhir:      { ... }   # (optional) tune the FHIR bundle output
omop:      { ... }   # (optional) tune the OMOP CDM output
```

1. **`adapter`** — identity metadata stamped onto every event's provenance.
2. **`match`** — a cheap routing check: does this config handle this record at all?
3. **`defaults`** — values shared by every emitted event (most importantly `subject_id`).
4. **`emit`** — a list of rules; each rule produces **0..n** events per input record.

## Required vs optional

| Block | Required? | If omitted |
|---|---|---|
| `adapter` | **Yes** | — |
| `match` | **Yes** | — |
| `defaults` | block optional, but **`subject_id` is mandatory** | engine cannot build events without a subject |
| `emit` | **Yes** | nothing is produced |
| `clean` | No | default chain: whitespace → timestamp_normalizer → type_coercer → unit_inferrer |
| `validate` | No | all five validators run against the global `quality_rules.yaml` |
| `qualify` | No | all five cross-event checks run with default tunables |
| `fhir` | No | FHIR output enabled with default resources (Patient + Observation + Questionnaire, transaction bundle) |
| `omop` | No | OMOP output enabled with all five CDM tables |

!!! tip "Prefer the smallest config that works"
    `fhir:` and `omop:` should be **absent** from almost every config — their defaults are
    already the standard output. Add them only when you explicitly need to change the output
    (drop a table, add a Provenance/Device resource, switch to a collection bundle). Likewise,
    only add a `validate.categories` override when your source genuinely deviates from the
    global rules.

## The smallest viable config

```yaml
adapter:
  id: "my-source-v1"
  version: "1.0.0"
  description: "One measurement per record from My Source"

match:
  source: "my-source"          # must equal the request's source name
  record:
    - { field: "userId", exists: true }

defaults:
  subject_id: { path: "userId" }   # bind a real person identifier

emit:
  - id: "reading"
    type: "measurement"
    category: "heart-rate"
    granularity: "instant"
    timestamp:
      start: { path: "ts", transform: "iso_millis" }
    payload:
      value: { path: "bpm" }
      unit: "bpm"
```

That config has no `clean/validate/qualify/fhir/omop` blocks, so every downstream stage runs
with its defaults. It is a complete, runnable adapter.

## The mental model for `emit`

For each input record, the engine walks the `emit` list **in order**. For each rule it:

1. checks the rule's optional `when:` gate (skip if not met);
2. decides how many events the rule produces — one by default, or one per element if the rule
   uses `iterate:` / `iterate_object:`;
3. builds each event by resolving every field's [value spec](value-specs.md) against the record.

A rule can also link to a `parent:` rule, so events from one rule reference events from another.

## How to read the rest of these docs

- [Reference](reference.md) — every block and key, with required/optional status and defaults.
- [Value specs](value-specs.md) — the mini-language for binding data into fields.
- [Quality & flags](quality-and-flags.md) — how to attach quality flags and override rules.
- [Examples](examples.md) — complete annotated configs you can copy.
- [Cookbook](cookbook.md) — task-oriented recipes.
- [Diagnostics](diagnostics.md) — debugging a config that emits nothing.

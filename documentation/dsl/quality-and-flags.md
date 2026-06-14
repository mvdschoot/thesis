# Quality & flags

The pipeline never drops a record — it **tags** it. This page covers how your config attaches
quality flags, overrides per-category rules, and how those feed the conformance / completeness /
plausibility assessment (after Kahn et al. 2016).

## The global rules

Validation and qualification are driven by a central file, `backend/configs/quality_rules.yaml`,
indexed by canonical `category`. Each category can declare:

```yaml
heart-rate:
  expected_fields: [subject_id, timestamp, payload.value, payload.unit]
  unit_whitelist: [bpm]
  range: { min: 25, max: 230, on_violation: { severity: warning, code: HR_OUT_OF_RANGE } }
```

- **`expected_fields`** — used by the completeness check.
- **`unit_whitelist`** — allowed values of `payload.unit`.
- **`range`** — numeric bounds on `payload.value`, with the flag to emit on violation.

Plus two global sections:

```yaml
plausibility_thresholds:
  warning_count_for_review: 1     # WARNING count >= this -> "review"
timestamp_window:
  min: "2000-01-01"
  max: "now+1d"
```

Your config interacts with these rules in three ways: per-category overlays
([`validate.categories`](reference.md#validate-optional)), per-rule
[`quality_overrides`](#quality_overrides), and explicit [`quality.flags`](#quality-flags).

## `quality.flags`

A per-rule list of flags attached to every event the rule emits. Each flag is **unconditional** or
**conditional**.

### Unconditional flags

Emitted on every event from the rule:

```yaml
quality:
  flags:
    - code: "SYNTHETIC_TIMESTAMP"
      severity: "info"             # info | warning | error
      stage: "structured"
      message: "Source has no timestamp column; start synthesized"
```

### Conditional flags

Emitted only when `condition.path` equals `condition.equals` on the record:

```yaml
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
      message: "Subject attribution flagged ambiguous (attrib=1)"
```

### Conventional flag codes

These are conventions emitted by configs (the engine does not hardcode them):

| Code | When you add it |
|---|---|
| `SYNTHETIC_SUBJECT_ID` (info) | `subject_id` synthesized via `template:` because the source has no person identifier |
| `SYNTHETIC_TIMESTAMP` (info) | the source has no per-record timestamp and you set a literal one |
| `MANUAL_ENTRY` (info) | the source flags a record as manually entered |
| `AMBIGUOUS_SUBJECT` (warning) | the source flags subject attribution as uncertain |

The pipeline stages also emit their own flags automatically (e.g. `TIMEZONE_ASSUMED_UTC`,
`UNIT_INFERRED`, `DUPLICATE_EVENT`, `OUTLIER_HAMPEL`, `HR_OUT_OF_RANGE`). See
[Engine → The seven stages](../engine/stages.md) for the full catalogue.

## `quality_overrides`

A per-rule override of the global `quality_rules.yaml` for this rule's category. Use it when a
single rule needs different bounds/units than the global category rule and a
`validate.categories` overlay would be too broad.

```yaml
emit:
  - id: "special-hr"
    category: "heart-rate"
    quality_overrides:
      range: { min: 30, max: 220, on_violation: { severity: info, code: HR_NOTE } }
    # ...
```

Internally this is carried on the event as a `_quality_override` extension, consumed by the
validator and then stripped before the response (it never appears in the output JSON).

## How flags become an assessment

The **qualifier** stage derives three summary fields on every event from the accumulated flags:

| Field | Values | Derivation |
|---|---|---|
| `quality.conformance` | `ok` / `issues` | `issues` if any non-info conformance-type flag exists (range, unit, timestamp, missing-field, payload-shape) |
| `quality.completeness` | ratio `0.0–1.0` | `present_field_count / expected_field_count` for the category |
| `quality.plausibility` | `ok` / `review` / `exclude` | any ERROR → `exclude`; else WARNING count ≥ `warning_count_for_review` → `review`; else `ok` |

`plausibility` is the field downstream consumers filter on — and it drives the FHIR Observation
`status` and whether a row is emitted to OMOP. See
[Engine → The seven stages](../engine/stages.md#4-qualifier).

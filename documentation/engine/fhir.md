# FHIR projection

The FHIR builder turns mapped canonical events into a FHIR R4 Bundle. It is configured by the
optional [`fhir`](../dsl/reference.md#fhir-optional-omit-by-default) block, but most of its
behavior is **hardcoded** mapping logic that is intentionally not configurable — terminology
binding is the mapper's job, and the resource shapes are fixed by FHIR R4.

## What the block controls

```yaml
fhir:
  enabled: true                 # default true
  bundle_type: transaction      # transaction (default) | collection
  include: [Patient, Observation, Questionnaire]   # default
```

- **`enabled: false`** returns no bundle.
- **`bundle_type: transaction`** adds `entry.request.method/url` (POST-able to a FHIR server);
  `collection` omits the request slice.
- **`include`** selects resource kinds from `[Patient, Observation, Device, Provenance,
  Questionnaire]`. Add `Device` when `context.device` is meaningful; add `Provenance` for an audit
  trail.

## Hardcoded mapping rules

These are *not* configurable here:

| Aspect | Rule |
|---|---|
| Resource kind | `type=measurement\|observation\|event\|session\|summary` → **Observation**; `type=survey` → **QuestionnaireResponse** |
| Status | `plausibility="exclude"` → `entered-in-error`; `"review"` → `amended`; otherwise → `final` |
| Headline value | `payload.value` → `valueQuantity` (numeric) / `valueBoolean` / `valueString` |
| Components | `payload.components[]` → `Observation.component[]` or `QuestionnaireResponse.item[]` |
| Effective time | both `timestamp` + `timestamp_end` → `effectivePeriod`; otherwise `effectiveDateTime` |
| Codes | every CodeableConcept is **text-only** unless the user bound a code via the mapper (LOINC for codes, UCUM for unit quantities) |
| Category | auto-bound to a standard observation-category (vital-signs / activity / exam / survey) unless overridden in the mapper |
| References | Subject / Device / Observation references are stable **UUID5** derivations of `subject_id`, `(source, device)`, and `event_id` — re-running produces identical URIs |
| Quality | quality flags + conformance/completeness travel as a custom extension / Provenance |

## Resources

- **Patient** — one per unique `subject_id`.
- **Observation** — one per non-survey event.
- **QuestionnaireResponse** — one per survey event; **Questionnaire** definitions are one per
  unique survey category.
- **Device** — one per unique `context.device` (only if included and present).
- **Provenance** — captures adapter metadata + quality (only if included).

## Why text-only codes by default

The FHIR stage runs *before* a human has necessarily reviewed terminology bindings. Rather than
guess codes, it emits text-only CodeableConcepts and lets the [mapper](stages.md#5-mapper) +
concept-binding UI attach LOINC/UCUM codes when the user confirms them. This keeps the "tag, don't
fabricate" discipline end to end.

The bundle is returned under `stats.fhir.bundle` and surfaced as the response's top-level
`bundle`. The frontend can POST it to the bundled HAPI FHIR server directly.

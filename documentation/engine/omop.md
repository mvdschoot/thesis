# OMOP projection

The OMOP builder projects mapped canonical events into OMOP CDM v5.4 tables. It is configured by
the optional [`omop`](../dsl/reference.md#omop-optional-omit-by-default) block; the table-routing
and concept-resolution logic is hardcoded. Unlike the FHIR builder, the OMOP stage does **not**
mutate events.

## What the block controls

```yaml
omop:
  enabled: true                 # default true
  include: [person, measurement, observation, device_exposure, observation_period]   # default all five
```

- **`enabled: false`** returns no OMOP tables.
- **`include`** selects which of the five clinical tables to emit. A custom `concept` table is
  always emitted alongside when custom (non-standard) codes exist — it is not gated.

## The tables

| Table | One row per | Notes |
|---|---|---|
| `person` | unique `subject_id` | demographics unknown for wearable data (`concept_id=0`) |
| `measurement` | numeric event routed to the Measurement domain | HR, weight, BP, steps, SpO2, … |
| `observation` | categorical/behavioural event | surveys, game scores, session metadata; fallback for non-Measurement domains |
| `device_exposure` | unique `(subject, device)` pair | |
| `observation_period` | subject | spans earliest→latest timestamp of that subject's rows |
| `concept` | custom code | OMOP 2-billion custom concepts for codes that don't resolve to a standard vocabulary |

## Hardcoded behavior

| Aspect | Rule |
|---|---|
| Table routing | domain-driven via the OMOPHub **FHIR Resolver** (`POST /v1/fhir/resolve/batch`); the response's `target_table` decides the table. A LOINC lab code routes to `measurement`, not `observation`. |
| Concept ids | both `*_concept_id` (standard, via "Maps to") and `*_source_concept_id` (original vocabulary) are populated |
| Type concept | `*_type_concept_id` derived from `context.modality`: wearable/sensor/app/game/vr → 32865 (self-report), scale → 705183 (self-tested), survey → 32862 (filled survey), unknown → 32817 (EHR) |
| Excluded events | events with `quality.plausibility="exclude"` are skipped entirely |
| Unmapped events | events that don't resolve (`concept_id=0`) are still emitted (OMOP convention) and tracked in a separate `unmapped` audit list |
| Components | `payload.components[]` (e.g. BP systolic/diastolic) become separate rows in the target table |

## Dependency on OMOPHub

Domain routing and concept resolution call the external OMOPHub API. When `OMOPHUB_API_KEY` is
unset, the pipeline still runs but OMOP rows get `concept_id=0` and routing falls back to the
default table. Terminology search in the UI is likewise unavailable. See
[Getting started](../getting-started.md#prerequisites).

The tables are returned under `stats.omop` and surfaced as the response's `omop_cdm`.

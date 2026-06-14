# Engine overview

The engine is the generic machinery that interprets your [config](../dsl/overview.md) and runs
every record through seven harmonization stages. It is a single in-process Python pipeline — no
message broker, no workers, no persistence between requests.

## Orchestration

One HTTP request to `POST /api/transform` calls `run_pipeline(...)`
(`backend/pipeline/__init__.py`), which chains the stages as plain function calls:

```
parse YAML  ──► ConfigAdapter
                    │
 connector.run  ──► (SourceMetadata, list[record])
 adapter.run    ──► CanonicalEvent[stage=STRUCTURED]   + diagnostics
 cleaner.run    ──► stage=CLEANED
 validator.run  ──► stage=VALIDATED
 qualifier.run  ──► stage=QUALIFIED                    + stats
 (strip internal _quality_override keys)
 mapper.run     ──► stage=MAPPED                       + concept slots
 fhir.run       ──► stage=STANDARDIZED                 + FHIR bundle
 omop.run       ──► (events unchanged)                 + OMOP CDM tables
                    │
 HTTP response: events + stats + bundle? + omop_cdm? + concept_slots + adapter_diagnostics
```

The YAML is parsed once; the optional `clean` / `validate` / `qualify` / `fhir` / `omop` blocks are
forwarded to their matching stages as parsed config objects.

## Design invariants

These hold across every stage and are load-bearing for the thesis story:

- **Tag, don't drop.** No stage filters events. A record that fails validation stays in the output
  carrying ERROR flags; the qualifier marks it `plausibility="exclude"` so consumers choose their
  own filter point.
- **Trail of evidence.** `payload.raw_value` is preserved through every stage. `quality.flags` is
  append-only — a flag is never removed.
- **Monotonic stages.** Each stage stamps its own `Stage` enum value; an event's `stage` field is
  the last stage it reached. The order is fixed:
  `raw → structured → cleaned → validated → qualified → mapped → standardized`.
- **Stateless.** No database, no shared state between requests. The qualifier's outlier detection
  therefore only sees the events in the current request — a known limitation, not a bug.
- **Internal plumbing is hidden.** Extension keys with a leading underscore (e.g.
  `_quality_override`, `_concept_codings`) are cross-stage hand-off and are stripped from the
  public event JSON by `CanonicalEvent.to_dict()`.
- **FHIR and OMOP are parallel projections.** Both run after the mapper on the same mapped events.
  FHIR stamps `STANDARDIZED`; OMOP does not further mutate events.

## The data quality frame

The qualifier classifies every event along three axes from Kahn et al. 2016 —
**conformance**, **completeness**, **plausibility** — recorded on `event.quality`. This is the
backbone of the "progressive harmonization with an audit trail" claim.

## Read next

- [The seven stages](stages.md) — what each stage does, in detail.
- [Canonical event](canonical-event.md) — the exact JSON shape every stage operates on.
- [FHIR projection](fhir.md) and [OMOP projection](omop.md) — the two output stages.
- [API contract](api.md) — request/response schemas.

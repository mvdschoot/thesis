# Progressive Harmonization — DSL & Engine Reference

This site documents the **YAML adapter-config DSL** and the **harmonization pipeline
engine** that powers this thesis-grade ETL web app. It is written for someone who wants to
point the app at a *new* data source and author their own adapter config — no Python
required.

## What the app does

The app turns heterogeneous health and behavioural data — Fitbit and Withings exports,
app-usage logs, linguistic games, a virtual supermarket, clinical pilot CSVs, questionnaires —
into:

1. a single **canonical event model**,
2. a **FHIR R4** Bundle, and
3. **OMOP CDM v5.4** tables,

all driven by a declarative YAML config. No source-specific Python is written per source; one
generic engine interprets your config.

## The core idea: progressive harmonization

Every record advances through seven explicit stages, and each stage leaves an audit trail of
quality flags rather than silently dropping data:

```
raw → structured → cleaned → validated → qualified → mapped → standardized
```

The governing principle is **tag, don't drop**: a record that fails validation stays in the
output carrying error flags, so downstream consumers decide their own filter point. The data
quality vocabulary (conformance / completeness / plausibility) follows Kahn et al. 2016.

## How a config drives the pipeline

```
your YAML config ─┐
                  ▼
 raw data ──► connector ──► adapter ──► cleaner ──► validator ──► qualifier ──► mapper ──► FHIR  ─┐
                            (DSL)       (clean:)    (validate:)   (qualify:)            (fhir:)   ├─► response
                                                                                        └► OMOP ──┘
                                                                                          (omop:)
```

Your config has a required core (`adapter`, `match`, `defaults`, `emit`) plus optional blocks
(`clean`, `validate`, `qualify`, `fhir`, `omop`) that tune each downstream stage. Omit the
optional blocks and the stages run with sensible defaults.

## Where to go next

| If you want to… | Read |
|---|---|
| Install and run the app, then transform your first record | [Getting started](getting-started.md) |
| Understand the shape of a config before diving into syntax | [DSL → Overview](dsl/overview.md) |
| Look up every block and key | [DSL → Reference](dsl/reference.md) |
| Learn the value-spec mini-language (paths, transforms, templates, lookups) | [DSL → Value specs](dsl/value-specs.md) |
| Copy a working config and adapt it | [DSL → Examples](dsl/examples.md) |
| Solve a specific mapping task (split date+time, survey columns, …) | [DSL → Cookbook](dsl/cookbook.md) |
| Debug "my config emitted 0 events" | [DSL → Diagnostics](dsl/diagnostics.md) |
| Understand what each pipeline stage actually does | [Engine → The seven stages](engine/stages.md) |
| See the exact JSON shape of an emitted event | [Engine → Canonical event](engine/canonical-event.md) |

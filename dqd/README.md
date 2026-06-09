# Harmonia — OHDSI DataQualityDashboard (DQD) test harness

External, third-party validation of Harmonia's OMOP CDM v5.4 output using the
official OHDSI [DataQualityDashboard](https://ohdsi.github.io/DataQualityDashboard/index.html).

DQD runs ~20 parameterised check types (which expand to thousands of individual
checks) across the three Kahn et al. 2016 data-quality categories —
**Conformance**, **Completeness**, **Plausibility** — at the **TABLE**, **FIELD**
and **CONCEPT** levels. This harness loads the files Harmonia exports into a local
**SQLite** database (no Java/JDBC, fully offline) and runs the full batch.

> **Backend note:** SQLite is used rather than DuckDB. DuckDB is the more modern
> OHDSI file backend, but the current DuckDB engine (1.5.x) corrupts process
> memory and hard-crashes R partway through a full DQD run. RSQLite is stable and
> is a long-standing DQD backend (Eunomia), so the harness uses it.

## Prerequisites

- R ≥ 4.0 (RStudio recommended — open `dqd.Rproj`)
- No Java required for the database. (DQD's `DatabaseConnector` loads `rJava`
  at startup, which needs *a* JDK present; `R/java_setup.R` auto-detects a
  working JDK and repairs a stale `JAVA_HOME` for the session — you normally
  don't have to touch this.)

## How it works

```
input/omop_cdm.json (or *.csv)  ──►  SQLite (CDM v5.4 DDL)  ──►  executeDqChecks()  ──►  output/dqd/results.json
                                       + synthesised cdm_source                          + results.csv + Shiny dashboard
```

DQD cannot read files directly — it executes SQL through `DatabaseConnector`. So
we materialise the canonical CDM v5.4 DDL (`CommonDataModel::createDdl`, with
`NOT NULL` relaxed so missing-required-field gaps are *reported* rather than
blocking the load) in a SQLite file, load Harmonia's tables, then run the checks.

## Step 1 — Export from Harmonia

In the Harmonia UI, transform a dataset (e.g. a Fitabase CSV from `sample_data/`),
open the **OMOP** results tab, then either:

- **"Download All"** → `omop_cdm.json` (recommended — one file, all tables), **or**
- the per-table **"CSV"** button for each table → `person.csv`, `measurement.csv`,
  `observation.csv`, `device_exposure.csv`, `observation_period.csv`,
  `concept.csv`.

Drop the file(s) into **`dqd/input/`**. If `omop_cdm.json` is present it wins;
otherwise the harness reads the CSVs.

## Step 2 — Install dependencies (once)

```r
source("R/install_dependencies.R")
```

Installs `DataQualityDashboard`, `DatabaseConnector`, `SqlRender`,
`CommonDataModel`, `RSQLite`, `DBI`, `jsonlite`, `here`.

## Step 3 — Run the checks

```r
source("R/run_dqd.R")
```

This (re)builds `output/harmonia_cdm.sqlite` from your input, runs the full DQD
batch, writes `output/dqd/results.json` + `results.csv`, and prints a summary
broken down by status and Kahn category.

## Step 4 — View the dashboard

```r
source("R/view_results.R")
```

Opens the bundled DQD Shiny dashboard on the latest results.

## Vocabulary (optional — enables CONCEPT-level checks)

The CONCEPT-level checks (`isStandardValidConcept`, `fkDomain`, `fkClass`,
`standardConceptRecordCompleteness`, concept/unit plausibility) and the
`isForeignKey` checks on `*_concept_id` columns need the OHDSI vocabulary. To
enable them, download the vocabulary CSVs from [Athena](https://athena.ohdsi.org/)
and place them in **`dqd/vocab/`** (tab-delimited).

The harness loads a **lean set** — `CONCEPT.csv` plus the small `VOCABULARY`,
`DOMAIN`, `CONCEPT_CLASS`, `RELATIONSHIP` lookups (see `VOCAB_TABLES` in
`R/load_cdm.R`). The multi-GB `CONCEPT_ANCESTOR` / `CONCEPT_RELATIONSHIP` /
`CONCEPT_SYNONYM` files are **not** loaded: no default DQD v5.4 check queries them
(the only ancestor-using check, `plausibleGenderUseDescendants`, is not
instantiated by the default threshold CSV). It is fine to leave those large files
in `dqd/vocab/` — they are simply skipped.

- **`CONCEPT.csv` present** → all three levels run (TABLE + FIELD + CONCEPT).
- **`CONCEPT.csv` absent** → TABLE + FIELD only (still the majority of checks).

Both `R/run_dqd.R` and `R/run_dqd_batch.R` auto-detect this — no code change needed.

## Interpreting the results (expected findings)

Harmonia's output is loaded **as-is** — the harness only synthesises the
mandatory `cdm_source` row (DQD crashes on an empty one). Several DQD failures
are therefore *expected* and are genuine findings for the thesis, not harness
bugs:

| Finding | Why | Check(s) |
|---|---|---|
| `person.year_of_birth = 0`, `gender_concept_id = 0` | Harmonia extracts no demographics from PGHD | `isRequired`, `plausibleValueLow`, `plausibleGenderUseDescendants` |
| Many `*_concept_id = 0` rows | unmapped source codes (no terminology binding) | `standardConceptRecordCompleteness`, `isStandardValidConcept` (vocab mode) |
| Missing CDM tables (visit_occurrence, death, …) | Harmonia produces a 6-table subset | `cdmTable` |
| `device_concept_id = 0` | device identifiers not mapped to OMOP vocab | `standardConceptRecordCompleteness` |

Structural/temporal checks that should **pass** demonstrate the pipeline is
sound: primary-key uniqueness (`isPrimaryKey`), foreign-key integrity to
`person`/`observation_period` (`isForeignKey`), and `plausibleStartBeforeEnd`
on `observation_period`. (Note: SQLite is dynamically typed, so `cdmDatatype`
conformance is checked less strictly than on a strongly-typed RDBMS.)

## Layout

```
dqd/
  R/
    install_dependencies.R   # one-time package install
    java_setup.R             # auto-repair JAVA_HOME so rJava (a DatabaseConnector
                             #   dependency) can load; sourced by the other scripts
    load_cdm.R               # build_cdm_sqlite(): read export → SQLite CDM v5.4
    run_dqd.R                # main: load → executeDqChecks → summary
    view_results.R           # open Shiny dashboard on latest results
  input/                     # drop omop_cdm.json or per-table CSVs here
  vocab/                     # optional Athena vocabulary CSVs
  output/                    # DuckDB + DQD results (gitignored)
  dqd.Rproj
```

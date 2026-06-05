# load_cdm.R
# ---------------------------------------------------------------------------
# Build a local SQLite OMOP CDM v5.4 database from Harmonia's export, ready for
# DataQualityDashboard.
#
# Backend choice: SQLite (via DatabaseConnector dbms = "sqlite" / RSQLite).
# DuckDB is the more "modern" OHDSI file backend, but the installed DuckDB
# engine (1.5.x) corrupts process memory and hard-crashes R (0xC0000005)
# partway through a full DQD run. RSQLite is pure-C-stable and DQD historically
# runs against SQLite (Eunomia), so we use it here — no Java/JDBC either.
#
# Input (in dqd/input/), in priority order:
#   1. omop_cdm.json    — the frontend's "Download All" export
#   2. <table>.csv       — per-table CSV downloads (person.csv, ...)
#
# Harmonia produces six CDM tables: person, measurement, observation,
# device_exposure, observation_period, concept (custom 2-billion concepts).
# It does NOT emit cdm_source — DQD crashes on an empty cdm_source
# (OHDSI/DataQualityDashboard#173) — so we synthesise one row.
#
# Data is loaded AS-IS (no patching): missing demographics (year_of_birth = 0,
# gender_concept_id = 0) and concept_id = 0 rows are real Harmonia output and
# their DQD failures are genuine findings.
#
# Entry point:  build_cdm_sqlite(input_dir, db_path, vocab_dir = NULL)
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(jsonlite)
})

# The CDM tables Harmonia exports (keys to keep from omop_cdm.json; the JSON
# also carries non-CDM extras — unmapped, stats, resolution_stats — we ignore).
HARMONIA_TABLES <- c(
  "person", "measurement", "observation",
  "device_exposure", "observation_period", "concept"
)

# Athena vocabulary tables we load when a vocab/ folder is supplied.
VOCAB_TABLES <- c(
  "CONCEPT", "VOCABULARY", "DOMAIN", "CONCEPT_CLASS",
  "CONCEPT_RELATIONSHIP", "RELATIONSHIP", "CONCEPT_SYNONYM",
  "CONCEPT_ANCESTOR"
)

# ---------------------------------------------------------------------------
# Input reading
# ---------------------------------------------------------------------------

#' Read the exported CDM tables from input_dir into a named list of data.frames.
#' Returns only tables that are present and non-empty.
read_harmonia_export <- function(input_dir) {
  json_path <- file.path(input_dir, "omop_cdm.json")
  tables <- list()

  if (file.exists(json_path)) {
    message("Reading export: ", json_path)
    raw <- jsonlite::fromJSON(json_path, simplifyDataFrame = TRUE)
    for (tbl in HARMONIA_TABLES) {
      df <- raw[[tbl]]
      if (!is.null(df) && is.data.frame(df) && nrow(df) > 0) {
        tables[[tbl]] <- df
      }
    }
  } else {
    csvs <- list.files(input_dir, pattern = "\\.csv$", full.names = TRUE)
    if (length(csvs) == 0) {
      stop(
        "No input found. Drop either omop_cdm.json or per-table CSVs ",
        "(person.csv, measurement.csv, ...) into: ", input_dir,
        call. = FALSE
      )
    }
    for (path in csvs) {
      tbl <- tolower(tools::file_path_sans_ext(basename(path)))
      if (tbl %in% HARMONIA_TABLES) {
        message("Reading CSV: ", basename(path))
        df <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE,
                       colClasses = "character", na.strings = c("NA"))
        if (nrow(df) > 0) tables[[tbl]] <- df
      }
    }
  }

  if (length(tables) == 0) {
    stop("Input present but no recognised CDM tables had rows.", call. = FALSE)
  }
  message("Loaded tables: ", paste(names(tables), collapse = ", "))
  tables
}

# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

#' Coerce a data.frame's columns to SQLite-appropriate values.
#' SQLite has no date type; SqlRender's sqlite date functions operate on ISO
#' text, so dates/datetimes are kept as 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS'
#' strings (NOT R Date objects, which RSQLite would store as numbers and break
#' the date SQL). *_id / *_concept_id / year_of_birth / *_as_number -> numeric.
#' Empty strings -> NA.
coerce_omop_types <- function(df) {
  for (col in names(df)) {
    v <- as.character(df[[col]])
    v[v == ""] <- NA
    lc <- tolower(col)
    if (grepl("_datetime$", lc)) {
      df[[col]] <- gsub("T", " ", substr(v, 1, 19))
    } else if (grepl("_date$", lc)) {
      df[[col]] <- substr(v, 1, 10)
    } else if (grepl("(_id$|_concept_id$|_as_number$)", lc) || lc == "year_of_birth") {
      df[[col]] <- suppressWarnings(as.numeric(v))
    } else {
      df[[col]] <- v
    }
  }
  df
}

# ---------------------------------------------------------------------------
# cdm_source synthesis
# ---------------------------------------------------------------------------

#' DQD reads CDM version/source metadata from cdm_source and errors if it is
#' empty. Insert a single descriptive row. cdm_version_concept_id 756265 is the
#' standard concept for "OMOP CDM Version 5.4".
synth_cdm_source <- function(conn, source_name) {
  row <- data.frame(
    cdm_source_name              = source_name,
    cdm_source_abbreviation      = "HARMONIA",
    cdm_holder                   = "Harmonia thesis ETL",
    source_description           = "Patient-generated health data harmonised by Harmonia.",
    source_documentation_reference = NA_character_,
    cdm_etl_reference            = "Harmonia",
    source_release_date          = "2024-01-01",
    cdm_release_date             = "2024-01-01",
    cdm_version                  = "5.4",
    cdm_version_concept_id       = 756265,
    vocabulary_version           = "Harmonia-custom",
    stringsAsFactors = FALSE
  )
  DatabaseConnector::insertTable(
    connection = conn, databaseSchema = "main", tableName = "cdm_source",
    data = row, createTable = FALSE, dropTableIfExists = FALSE,
    progressBar = FALSE, camelCaseToSnakeCase = FALSE
  )
  message("Synthesised cdm_source (1 row).")
}

# ---------------------------------------------------------------------------
# Optional Athena vocabulary load
# ---------------------------------------------------------------------------

#' Load Athena vocabulary CSVs (tab-delimited) into the CDM vocab tables.
#' Returns TRUE if a vocabulary was found. NOTE: large vocabularies (CONCEPT,
#' CONCEPT_ANCESTOR can be millions of rows) load slowly into SQLite — expect
#' minutes. Only needed for CONCEPT-level checks.
load_vocabulary <- function(conn, vocab_dir) {
  if (is.null(vocab_dir) || !dir.exists(vocab_dir)) return(FALSE)
  concept_csv <- file.path(vocab_dir, "CONCEPT.csv")
  if (!file.exists(concept_csv)) {
    message("No CONCEPT.csv in vocab/ — running without vocabulary (TABLE+FIELD only).")
    return(FALSE)
  }
  for (tbl in VOCAB_TABLES) {
    path <- file.path(vocab_dir, paste0(tbl, ".csv"))
    if (!file.exists(path)) {
      message("  (skip vocab ", tbl, " — file absent)")
      next
    }
    message("Loading vocabulary ", tbl, " (this can take a while) ...")
    df <- tryCatch(
      utils::read.delim(path, sep = "\t", quote = "", stringsAsFactors = FALSE,
                        check.names = FALSE, na.strings = c("")),
      error = function(e) {
        warning("Could not read vocab ", tbl, ": ", conditionMessage(e)); NULL
      }
    )
    if (is.null(df) || nrow(df) == 0) next
    names(df) <- tolower(names(df))
    DatabaseConnector::insertTable(
      connection = conn, databaseSchema = "main", tableName = tolower(tbl),
      data = df, createTable = FALSE, dropTableIfExists = FALSE,
      progressBar = FALSE, camelCaseToSnakeCase = FALSE
    )
    message("  loaded ", tbl, " ", nrow(df), " rows")
  }
  TRUE
}

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

#' Build a SQLite CDM v5.4 database from a Harmonia export.
#'
#' @param input_dir directory holding omop_cdm.json or per-table CSVs
#' @param db_path   path to the SQLite file to (re)create
#' @param vocab_dir optional directory of Athena vocabulary CSVs
#' @return list(connectionDetails, vocab_loaded, row_counts)
build_cdm_sqlite <- function(input_dir, db_path, vocab_dir = NULL) {
  tables <- read_harmonia_export(input_dir)

  # Fresh DB each run for idempotency.
  if (file.exists(db_path)) file.remove(db_path)
  dir.create(dirname(db_path), recursive = TRUE, showWarnings = FALSE)

  connectionDetails <- DatabaseConnector::createConnectionDetails(
    dbms = "sqlite", server = db_path
  )

  conn <- DatabaseConnector::connect(connectionDetails)
  on.exit(DatabaseConnector::disconnect(conn), add = TRUE)

  # 1. Materialise the CDM v5.4 tables (typed columns). We generate the DDL and
  #    relax it for this file-based test harness:
  #      * strip NOT NULL  -> let DQD's isRequired check REPORT missing required
  #        fields (e.g. observation_period.period_type_concept_id, which
  #        Harmonia leaves null) instead of the load crashing on the constraint.
  #      * the DDL has no ALTER-TABLE PK/FK steps here; DQD evaluates keys via
  #        SQL (isPrimaryKey / isForeignKey) regardless of DB-enforced keys.
  message("Creating CDM v5.4 tables in SQLite ...")
  ddl <- CommonDataModel::createDdl("5.4")
  ddl <- SqlRender::render(ddl, cdmDatabaseSchema = "main",
                           warnOnMissingParameters = FALSE)
  ddl <- SqlRender::translate(ddl, targetDialect = "sqlite")
  ddl <- gsub("\\bNOT\\s+NULL\\b", "", ddl, ignore.case = TRUE)
  DatabaseConnector::executeSql(conn, ddl, progressBar = FALSE,
                                reportOverallTime = FALSE)

  # 2. Load Harmonia's tables.
  row_counts <- list()
  for (tbl in names(tables)) {
    df <- coerce_omop_types(tables[[tbl]])
    DatabaseConnector::insertTable(
      connection = conn, databaseSchema = "main", tableName = tbl,
      data = df, createTable = FALSE, dropTableIfExists = FALSE,
      progressBar = FALSE, camelCaseToSnakeCase = FALSE
    )
    row_counts[[tbl]] <- nrow(df)
    message(sprintf("  loaded %-20s %d rows", tbl, nrow(df)))
  }

  # 3. Synthesise cdm_source (mandatory for DQD).
  synth_cdm_source(conn, "Harmonia OMOP Export")

  # 4. Optional Athena vocabulary.
  vocab_loaded <- load_vocabulary(conn, vocab_dir)

  list(
    connectionDetails = connectionDetails,
    vocab_loaded      = vocab_loaded,
    row_counts        = row_counts
  )
}

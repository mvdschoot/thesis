# run_dqd.R
# ---------------------------------------------------------------------------
# Main entry point: load Harmonia's OMOP export into SQLite, run the full
# DataQualityDashboard batch, and print a Kahn-category summary.
#
#   source("R/run_dqd.R")
#
# Reads from dqd/input/, writes results to dqd/output/dqd/.
# If dqd/vocab/ contains Athena CSVs, CONCEPT-level checks are included;
# otherwise only TABLE + FIELD checks run.
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(here)
})

# Repair JAVA_HOME for rJava BEFORE DatabaseConnector loads it.
source(file.path(here::here(), "R", "java_setup.R"))

suppressPackageStartupMessages({
  library(DatabaseConnector)
  library(DataQualityDashboard)
})

# Project-root-relative paths (works regardless of getwd()).
ROOT       <- here::here()
INPUT_DIR  <- file.path(ROOT, "input")
VOCAB_DIR  <- file.path(ROOT, "vocab")
OUTPUT_DIR <- file.path(ROOT, "output")
DB_PATH    <- file.path(OUTPUT_DIR, "harmonia_cdm.sqlite")
DQD_OUT    <- file.path(OUTPUT_DIR, "dqd")

source(file.path(ROOT, "R", "load_cdm.R"))

dir.create(DQD_OUT, recursive = TRUE, showWarnings = FALSE)

# 1. Build the database.
built <- build_cdm_sqlite(
  input_dir = INPUT_DIR,
  db_path   = DB_PATH,
  vocab_dir = VOCAB_DIR
)

check_levels <- if (built$vocab_loaded) {
  c("TABLE", "FIELD", "CONCEPT")
} else {
  c("TABLE", "FIELD")
}
message("\nVocabulary loaded: ", built$vocab_loaded,
        " — running check levels: ", paste(check_levels, collapse = ", "))

# 2. Run the full DQD batch. No checkNames filter => every applicable check
#    runs. Tables Harmonia doesn't produce simply fail/NA their cdmTable check,
#    which is itself a finding worth reporting.
results <- DataQualityDashboard::executeDqChecks(
  connectionDetails     = built$connectionDetails,
  cdmDatabaseSchema     = "main",
  resultsDatabaseSchema = "main",
  vocabDatabaseSchema   = "main",
  cdmSourceName         = "Harmonia OMOP Export",
  cdmVersion            = "5.4",
  checkLevels           = check_levels,
  outputFolder          = DQD_OUT,
  outputFile            = "results.json",
  writeToTable          = FALSE,
  writeToCsv            = FALSE,
  verboseMode           = FALSE
)

# Flat CSV of all check results (handy for spreadsheets / the thesis appendix).
# Written here rather than via writeToCsv, whose absolute-path handling is flaky.
utils::write.csv(results$CheckResults, file.path(DQD_OUT, "results.csv"),
                 row.names = FALSE)

# 3. Console summary for the thesis write-up.
print_summary <- function(results) {
  df <- results$CheckResults
  if (is.null(df) || nrow(df) == 0) {
    message("No check results returned.")
    return(invisible(NULL))
  }
  status <- ifelse(df$isError == 1, "ERROR",
                   ifelse(df$notApplicable == 1, "NOT_APPLICABLE",
                          ifelse(df$failed == 1, "FAIL", "PASS")))

  cat("\n==================== DQD SUMMARY ====================\n")
  cat("Total checks executed:", nrow(df), "\n\n")

  cat("By status:\n")
  print(table(status))

  if ("category" %in% names(df)) {
    cat("\nBy Kahn category (Conformance / Completeness / Plausibility):\n")
    print(table(df$category, status))
  }

  fails <- df[status == "FAIL", ]
  if (nrow(fails) > 0) {
    cat("\nFailing checks (", nrow(fails), "):\n", sep = "")
    cols <- intersect(
      c("checkName", "cdmTableName", "cdmFieldName", "pctViolatedRows", "thresholdValue"),
      names(fails)
    )
    show <- fails[order(-fails$pctViolatedRows), cols, drop = FALSE]
    print(utils::head(show, 40), row.names = FALSE)
  }
  cat("\nResults written to: ", DQD_OUT, "\n", sep = "")
  cat("View interactively:  source(\"R/view_results.R\")\n")
  cat("=====================================================\n")
}

print_summary(results)

# install_dependencies.R
# ---------------------------------------------------------------------------
# One-time setup for the Harmonia DQD test harness.
#
# DataQualityDashboard (DQD) executes its SQL through DatabaseConnector. We use
# a local SQLite database (the `RSQLite` package, no Java/JDBC required) so the
# whole harness runs offline against the CSV/JSON files Harmonia exports.
# (SQLite is used instead of DuckDB because the installed DuckDB engine crashes
# R mid-run; RSQLite is stable and is a long-standing DQD backend — Eunomia.)
#
# Run once:   source("R/install_dependencies.R")
# ---------------------------------------------------------------------------

# Installing DataQualityDashboard lazy-loads DatabaseConnector (-> rJava), so a
# usable JAVA_HOME must be in place BEFORE install, or the build fails. Repair
# it for this session first. (Run from the project root, e.g. via dqd.Rproj.)
local({
  setup <- if (file.exists("R/java_setup.R")) "R/java_setup.R" else "java_setup.R"
  source(setup)
})

required <- c(
  "DBI",          # generic DB interface
  "RSQLite",      # embedded SQLite DB (DatabaseConnector dbms = "sqlite")
  "DatabaseConnector",  # OHDSI DB layer DQD runs against
  "SqlRender",    # OHDSI dialect-aware SQL templating (DQD dependency)
  "CommonDataModel",    # ships the CDM v5.4 DDL we materialise in DuckDB
  "DataQualityDashboard",
  "jsonlite",     # parse Harmonia's omop_cdm.json
  "here"          # project-root-relative paths
)

installed <- rownames(installed.packages())
missing <- setdiff(required, installed)

if (length(missing) == 0) {
  message("All required packages already installed.")
} else {
  message("Installing: ", paste(missing, collapse = ", "))
  # CRAN has all of these; DataQualityDashboard, DatabaseConnector and
  # CommonDataModel are also on the OHDSI GitHub if a newer build is needed.
  install.packages(missing)
}

# Sanity check: confirm SQLite is wired into DatabaseConnector on this machine.
ok <- requireNamespace("DatabaseConnector", quietly = TRUE) &&
  requireNamespace("RSQLite", quietly = TRUE)
if (ok) {
  message("DatabaseConnector + RSQLite available — no Java/JDBC driver needed.")
} else {
  warning("DatabaseConnector or RSQLite failed to load; re-check installation.")
}

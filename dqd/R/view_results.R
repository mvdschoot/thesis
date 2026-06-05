# view_results.R
# ---------------------------------------------------------------------------
# Open the most recent DQD results.json in the bundled Shiny dashboard.
#
#   source("R/view_results.R")
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(here)
})

# Repair JAVA_HOME for rJava BEFORE DataQualityDashboard (→ DatabaseConnector) loads.
source(file.path(here::here(), "R", "java_setup.R"))

suppressPackageStartupMessages({
  library(DataQualityDashboard)
})

DQD_OUT <- file.path(here::here(), "output", "dqd")

jsons <- list.files(DQD_OUT, pattern = "\\.json$", full.names = TRUE,
                    recursive = TRUE)
if (length(jsons) == 0) {
  stop("No DQD results JSON found in ", DQD_OUT,
       " — run source(\"R/run_dqd.R\") first.", call. = FALSE)
}

# Newest by modification time.
latest <- jsons[order(file.info(jsons)$mtime, decreasing = TRUE)][1]
message("Opening dashboard for: ", latest)

DataQualityDashboard::viewDqDashboard(latest)

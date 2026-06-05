# java_setup.R
# ---------------------------------------------------------------------------
# DatabaseConnector loads rJava at namespace-load time, even though our DuckDB
# backend needs no JDBC/Java. rJava finds the JVM via JAVA_HOME\bin\server\jvm.dll
# (Windows). A stale or broken JAVA_HOME (e.g. an uninstalled JDK left behind)
# makes rJava.dll fail with "LoadLibrary failure: The specified module could not
# be found", which blocks the whole harness.
#
# ensure_java() validates JAVA_HOME and, if broken, repoints it to a working JDK
# found in the usual install locations — for THIS R session only (no system
# changes). MUST be called BEFORE library(DatabaseConnector) / library(rJava).
# ---------------------------------------------------------------------------

#' Path to the jvm.dll (Windows) / libjvm (Unix) under a JAVA_HOME, or NA.
.jvm_lib <- function(java_home) {
  if (is.na(java_home) || java_home == "" || !dir.exists(java_home)) return(NA_character_)
  candidates <- if (.Platform$OS.type == "windows") {
    file.path(java_home, c("bin/server/jvm.dll", "jre/bin/server/jvm.dll"))
  } else {
    file.path(java_home, c("lib/server/libjvm.so", "jre/lib/server/libjvm.so",
                           "lib/server/libjvm.dylib"))
  }
  hit <- candidates[file.exists(candidates)]
  if (length(hit) > 0) hit[1] else NA_character_
}

#' Find a working JDK by scanning common Windows install roots. Returns a
#' JAVA_HOME path whose jvm.dll exists, or NA.
.discover_jdk <- function() {
  roots <- c(
    "C:/Program Files/Eclipse Adoptium",
    "C:/Program Files/Java",
    "C:/Program Files/Microsoft",
    "C:/Program Files/Zulu",
    "C:/Program Files/OpenLogic",
    "C:/Program Files/Amazon Corretto"
  )
  roots <- roots[dir.exists(roots)]
  for (root in roots) {
    subdirs <- list.dirs(root, recursive = FALSE)
    # Prefer higher versions (later in sort order).
    subdirs <- subdirs[order(subdirs, decreasing = TRUE)]
    for (d in subdirs) {
      if (!is.na(.jvm_lib(d))) return(d)
    }
  }
  NA_character_
}

#' Ensure a usable JAVA_HOME for rJava in this session. Returns the JAVA_HOME in
#' effect (invisibly), or stops with guidance if none can be found.
ensure_java <- function() {
  current <- Sys.getenv("JAVA_HOME", unset = NA_character_)
  if (!is.na(.jvm_lib(current))) {
    return(invisible(current))  # already valid
  }

  if (!is.na(current) && current != "") {
    message("JAVA_HOME is set but invalid (no jvm.dll): ", current)
  }
  found <- .discover_jdk()
  if (is.na(found)) {
    stop(
      "No working JDK found. Install a 64-bit JDK (e.g. Eclipse Temurin 17/21 ",
      "from https://adoptium.net) and set JAVA_HOME to it, then restart R.",
      call. = FALSE
    )
  }

  message("Repointing JAVA_HOME -> ", found)
  Sys.setenv(JAVA_HOME = found)
  # Make jvm.dll discoverable to the loader for this session.
  jvm_dir <- dirname(.jvm_lib(found))
  Sys.setenv(PATH = paste(jvm_dir, Sys.getenv("PATH"), sep = .Platform$path.sep))
  invisible(found)
}

ensure_java()

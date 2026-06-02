"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AdapterPanel from "@/components/adapter/AdapterPanel";
import ConnectorPanel from "@/components/connector/ConnectorPanel";
import FhirServerPanel from "@/components/fhir/FhirServerPanel";
import PipelineNav from "@/components/PipelineNav";
import ResultsPanel from "@/components/results/ResultsPanel";
import StageStrip, { type StageDef } from "@/components/StageStrip";
import Topbar from "@/components/Topbar";
import {
  getConfig,
  listConfigs,
  matchConfigs,
  transform,
  updateConfig,
  type ConfigMatch,
  type Descriptor,
  type TransformFormat,
  type TransformResponse,
} from "@/lib/api";
import {
  splitIntoBatches,
  mergeResponses,
  sampleForMatch,
  sampleForScan,
  countRecords,
  CONCEPT_SCAN_THRESHOLD,
  type BatchProgress,
} from "@/lib/batch";
import { SAMPLE_CONFIGS, SIMULATED_EVENTS } from "@/lib/sampleData";
import type { AdapterConfig, CanonicalEvent, Coding } from "@/lib/types";
import { dumpAdapterYaml, parseAdapterYaml } from "@/lib/yaml";

const SAMPLE_CONFIG_KEYS = Object.keys(SAMPLE_CONFIGS);

export default function Page() {
  // Connector state — upload-only (JSON or CSV).
  const [customText, setCustomText] = useState<string>("");
  // Debounced copy of customText so JSON.parse / matchConfigs don't run on
  // every keystroke when the user pastes a multi-MB blob.
  const [debouncedCustomText, setDebouncedCustomText] = useState<string>("");
  const [customFormat, setCustomFormat] = useState<TransformFormat>("json");
  const [customSource, setCustomSource] = useState<string>("");
  const [customError, setCustomError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedCustomText(customText), 350);
    return () => clearTimeout(t);
  }, [customText]);

  // Adapter state — backend configs override the seeded SAMPLE_CONFIGS where available.
  const [configMap, setConfigMap] = useState<Record<string, AdapterConfig>>({ ...SAMPLE_CONFIGS });
  const [configKey, setConfigKey] = useState<string>(SAMPLE_CONFIG_KEYS[0] ?? "");
  const [backendIds, setBackendIds] = useState<string[]>([]);
  const [adapterLoading, setAdapterLoading] = useState(false);
  const [adapterError, setAdapterError] = useState<string | null>(null);
  // Descriptor files saved with each backend config, keyed by config id.
  const [descriptorMap, setDescriptorMap] = useState<Record<string, Descriptor[]>>({});

  // Stage navigation
  const [activeStage, setActiveStage] = useState<string>("connector");

  // Run state
  const [runResult, setRunResult] = useState<TransformResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // Concept-mapping state (session-only, sent on each /api/transform call).
  const [conceptMappings, setConceptMappings] = useState<Record<string, Coding>>({});
  const [conceptNoMatches, setConceptNoMatches] = useState<Record<string, import("@/lib/api").NoMatchSlot>>({});

  // Batch processing state
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const batchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Concept scan phase — true when we've done a lightweight slot scan on a
  // sample and are waiting for the user to map concepts before the full run.
  const [scanPhase, setScanPhase] = useState(false);

  // Config matching state — populated by /api/configs/match against the current input.
  const [configMatches, setConfigMatches] = useState<ConfigMatch[] | null>(null);

  // ── Load backend config list once on mount. Each id loads on first selection.
  useEffect(() => {
    let cancelled = false;
    listConfigs()
      .then((list) => {
        if (cancelled) return;
        const ids = list.map((c) => c.id);
        setBackendIds(ids);
        if (ids.length > 0 && !ids.includes(configKey)) {
          setConfigKey(ids[0]);
        }
      })
      .catch(() => {
        // Backend unreachable — fall back silently to SAMPLE_CONFIGS.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Lazy-load YAML for a backend config when it's selected.
  useEffect(() => {
    if (!configKey) return;
    if (configMap[configKey]) return;
    if (!backendIds.includes(configKey)) return;
    let cancelled = false;
    setAdapterLoading(true);
    setAdapterError(null);
    getConfig(configKey)
      .then((payload) => {
        if (cancelled) return;
        try {
          const parsed = parseAdapterYaml(payload.yaml);
          setConfigMap((m) => ({ ...m, [configKey]: parsed }));
          setDescriptorMap((m) => ({ ...m, [configKey]: payload.descriptors ?? [] }));
        } catch (e) {
          setAdapterError((e as Error).message);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setAdapterError(e.message);
      })
      .finally(() => {
        if (!cancelled) setAdapterLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [configKey, configMap, backendIds]);

  const config: AdapterConfig | null = configMap[configKey] ?? null;

  const setConfig = (next: AdapterConfig) => {
    setConfigMap((m) => ({ ...m, [configKey]: next }));
  };

  const onLLMResult = (yamlText: string, configId: string, descriptors: Descriptor[]) => {
    try {
      const parsed = parseAdapterYaml(yamlText);
      setConfigMap((m) => ({ ...m, [configId]: parsed }));
      setDescriptorMap((m) => ({ ...m, [configId]: descriptors }));
      setBackendIds((ids) => (ids.includes(configId) ? ids : [...ids, configId]));
      setConfigKey(configId);
    } catch (e) {
      setAdapterError((e as Error).message);
    }
  };

  // The active payload format — driven by the uploaded file's extension.
  const activeFormat: TransformFormat = customFormat;

  // ── Resolve the input data for transform.
  // For JSON: parsed object/array. For CSV: raw text passed through to the backend.
  // Reads from the debounced text so a paste of multi-MB JSON doesn't re-parse
  // on every keystroke.
  const inputData: unknown | null = useMemo(() => {
    if (!debouncedCustomText.trim()) return null;
    if (customFormat === "csv") return debouncedCustomText;
    try {
      return JSON.parse(debouncedCustomText) as unknown;
    } catch {
      return null;
    }
  }, [debouncedCustomText, customFormat]);

  // String form of inputData for endpoints that parse server-side (e.g.
  // /configs/match). We already have the raw text — skip re-stringifying the
  // parsed JSON (a wasted full pass on large payloads).
  const inputDataString: string | null = useMemo(() => {
    return debouncedCustomText.trim() ? debouncedCustomText : null;
  }, [debouncedCustomText]);

  // Validate custom payload for user feedback (non-blocking). Reads from the
  // debounced text so we don't JSON.parse a multi-MB blob on each keystroke.
  useEffect(() => {
    if (!debouncedCustomText.trim()) {
      setCustomError(null);
      return;
    }
    if (customFormat === "csv") {
      // Minimal sanity check: at least one newline-separated row of fields.
      const firstLine = debouncedCustomText.split(/\r?\n/, 1)[0] ?? "";
      if (!firstLine.includes(",")) {
        setCustomError("CSV looks malformed: no comma found in the header row.");
      } else {
        setCustomError(null);
      }
      return;
    }
    try {
      JSON.parse(debouncedCustomText);
      setCustomError(null);
    } catch (e) {
      setCustomError(`Invalid JSON: ${(e as Error).message}`);
    }
  }, [debouncedCustomText, customFormat]);

  // Source name describes the *data*, not the adapter. In sample mode it comes
  // from the fixture; in custom mode the user owns it. Don't fall back to the
  // currently-selected adapter's source — that's how an unrelated adapter's
  // `match.source` (e.g. "app-usage") leaks into transform requests and into
  // LLM-generated configs for other data.
  const sourceName = useMemo(() => customSource.trim(), [customSource]);

  // Reset scan phase whenever pipeline inputs change.
  useEffect(() => { setScanPhase(false); }, [inputData, configKey, activeFormat]);

  // Sampled version of input for config matching — first 50 records only.
  const matchSampleString: string | null = useMemo(() => {
    if (inputDataString == null) return null;
    return sampleForMatch(inputData, inputDataString, activeFormat);
  }, [inputData, inputDataString, activeFormat]);

  // ── Ask the backend which registered configs apply to the current input.
  // Debounced so paste/keystroke streams don't spam the endpoint. Failures
  // hide the panel rather than surface noise — same forgiving pattern as
  // listConfigs above. Only sends a small sample of the input data.
  useEffect(() => {
    if (matchSampleString == null) {
      setConfigMatches(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      matchConfigs(matchSampleString, activeFormat, sourceName || undefined)
        .then((res) => {
          if (!cancelled) setConfigMatches(res);
        })
        .catch(() => {
          if (!cancelled) setConfigMatches(null);
        });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [matchSampleString, activeFormat, sourceName]);

  const events: CanonicalEvent[] = runResult?.events ?? SIMULATED_EVENTS;
  const eventSource: "live" | "simulated" = runResult ? "live" : "simulated";
  const bundle = runResult?.bundle ?? null;
  const omopCdm = runResult?.omop_cdm ?? null;
  const conceptSlots = runResult?.concept_slots ?? [];
  const adapterDiagnostics = runResult?.adapter_diagnostics ?? null;

  // YAML text passed down so the DebugPanel can send the *current* config to
  // /api/suggest-config-fix. Stays in sync with edits in AdapterPanel via the
  // shared configMap state.
  const yamlText = useMemo(
    () => (config ? dumpAdapterYaml(config) : ""),
    [config],
  );

  // Apply an LLM-patched YAML back to the editor AND persist it to the backend
  // config store, so the fix survives re-runs and reloads — not just the
  // in-memory session. Sample/bundled configs have no backend file, so those
  // are updated locally only.
  const applyPatchedYaml = async (next: string) => {
    let parsed: AdapterConfig;
    try {
      parsed = parseAdapterYaml(next);
    } catch (e) {
      setRunError(`Patched YAML failed to parse: ${(e as Error).message}`);
      return;
    }
    setConfigMap((m) => ({ ...m, [configKey]: parsed }));
    setRunError(null);
    if (!backendIds.includes(configKey)) return;
    try {
      await updateConfig(configKey, dumpAdapterYaml(parsed));
    } catch (e) {
      setRunError(`Applied to the editor, but saving to the backend failed: ${(e as Error).message}`);
      throw e;
    }
  };

  // Single O(n) pass over events for the stage-strip flag counters. Kept
  // separate from stageDefs so flipping stages / editing the YAML doesn't
  // retraverse the event list.
  const flagTotals = useMemo(() => {
    let warn = 0;
    let err = 0;
    for (const e of events) {
      for (const f of e.quality.flags) {
        if (f.severity === "warning") warn++;
        else if (f.severity === "error") err++;
      }
    }
    return { warn, err };
  }, [events]);

  const stageDefs: StageDef[] = useMemo(() => {
    const total = events.length;
    const { warn, err } = flagTotals;
    const emitCount = config?.emit.length ?? 0;
    // Strip is Connector → Adapter → Results (3 columns, matches the CSS grid).
    return [
      {
        id: "connector",
        label: "Connector",
        count: 1,
        note: "upload",
        done: activeStage !== "connector",
        pulse: activeStage === "connector",
      },
      {
        id: "adapter",
        label: "Config",
        count: total,
        note: `${emitCount} emit rules`,
        done: activeStage === "results",
        pulse: activeStage === "adapter",
      },
      {
        id: "results",
        label: "Results",
        count: total,
        note: "FHIR · OMOP",
        warn,
        err,
        done: false,
        pulse: activeStage === "results",
      },
    ];
  }, [events, flagTotals, activeStage, config]);

  const canRun = inputData != null && config != null;

  const cancelBatch = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  async function handleRun(opts?: { preserveConcepts?: boolean }) {
    if (!canRun || !config) {
      setRunError("Need both input data and an adapter config before running.");
      return;
    }
    setRunError(null);
    setRunning(true);

    const yamlText = dumpAdapterYaml(config);
    const mappingsToSend = opts?.preserveConcepts ? conceptMappings : {};
    if (!opts?.preserveConcepts) {
      setConceptMappings({});
      setConceptNoMatches({});
    }

    // ── Concept-scan fast path for large inputs ──────────────────────────
    const recordCount = countRecords(inputData, activeFormat);
    if (
      !opts?.preserveConcepts &&
      Object.keys(mappingsToSend).length === 0 &&
      recordCount > CONCEPT_SCAN_THRESHOLD
    ) {
      setScanPhase(true);
      try {
        const sample = sampleForScan(inputData, activeFormat);
        const scanRes = await transform({
          data: sample,
          yaml: yamlText,
          source: sourceName || undefined,
          format: activeFormat,
          concept_scan_only: true,
        });
        setRunResult(scanRes);
        setActiveStage("results");
      } catch (e) {
        setScanPhase(false);
        setRunError((e as Error).message);
      } finally {
        setRunning(false);
      }
      return;
    }

    setScanPhase(false);

    const chunks = splitIntoBatches(inputData, activeFormat);

    if (chunks.length === 1) {
      // Single-request fast path — no batching overhead.
      try {
        const res = await transform({
          data: chunks[0].data,
          yaml: yamlText,
          source: sourceName || undefined,
          format: activeFormat,
          concept_mappings:
            Object.keys(mappingsToSend).length > 0 ? mappingsToSend : undefined,
        });
        setRunResult(res);
        setActiveStage("results");
      } catch (e) {
        setRunError((e as Error).message);
      } finally {
        setRunning(false);
        setBatchProgress(null);
      }
      return;
    }

    // Multi-batch path.
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current);
      batchTimeoutRef.current = null;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const partials: TransformResponse[] = [];
    let eventsProcessed = 0;

    setBatchProgress({
      batchIndex: 0,
      batchCount: chunks.length,
      eventsProcessed: 0,
      status: "running",
    });

    try {
      for (let i = 0; i < chunks.length; i++) {
        if (controller.signal.aborted) break;

        setBatchProgress({
          batchIndex: i,
          batchCount: chunks.length,
          eventsProcessed,
          status: "running",
        });

        const res = await transform(
          {
            data: chunks[i].data,
            yaml: yamlText,
            source: sourceName || undefined,
            format: activeFormat,
            concept_mappings:
              Object.keys(mappingsToSend).length > 0 ? mappingsToSend : undefined,
          },
          controller.signal,
        );

        partials.push(res);
        eventsProcessed += res.events.length;
      }

      if (controller.signal.aborted && partials.length > 0) {
        setRunResult(mergeResponses(partials));
        setRunError(
          `Cancelled after batch ${partials.length}/${chunks.length}. Showing partial results.`,
        );
      } else if (partials.length > 0) {
        setRunResult(mergeResponses(partials));
      }

      setBatchProgress({
        batchIndex: chunks.length - 1,
        batchCount: chunks.length,
        eventsProcessed,
        status: controller.signal.aborted ? "error" : "done",
      });
      setActiveStage("results");
    } catch (e) {
      const isAbort = e instanceof DOMException && e.name === "AbortError";
      if (isAbort) {
        if (partials.length > 0) {
          setRunResult(mergeResponses(partials));
          setRunError(
            `Cancelled after batch ${partials.length}/${chunks.length}. Showing partial results.`,
          );
        } else {
          setRunError("Cancelled.");
        }
      } else if (partials.length > 0) {
        setRunResult(mergeResponses(partials));
        setRunError(
          `Batch ${partials.length + 1}/${chunks.length} failed: ${(e as Error).message}. Showing partial results (batches 1–${partials.length}).`,
        );
      } else {
        setRunError((e as Error).message);
      }
      setBatchProgress({
        batchIndex: partials.length,
        batchCount: chunks.length,
        eventsProcessed,
        status: "error",
      });
      setActiveStage("results");
    } finally {
      setRunning(false);
      abortRef.current = null;
      batchTimeoutRef.current = setTimeout(() => {
        setBatchProgress(null);
        batchTimeoutRef.current = null;
      }, 2000);
    }
  }

  function handleConceptChange(key: string, coding: Coding | null) {
    setConceptMappings((prev) => {
      const next = { ...prev };
      if (coding === null) delete next[key];
      else next[key] = coding;
      return next;
    });
  }

  function handleBulkConceptChange(newMappings: Record<string, Coding>) {
    setConceptMappings((prev) => ({ ...prev, ...newMappings }));
  }

  function handleNoMatchesChange(newNoMatches: Record<string, import("@/lib/api").NoMatchSlot>) {
    setConceptNoMatches((prev) => ({ ...prev, ...newNoMatches }));
  }

  const configIds = useMemo(() => {
    const merged = new Set<string>([...SAMPLE_CONFIG_KEYS, ...backendIds]);
    return Array.from(merged);
  }, [backendIds]);

  // The FHIR Server dashboard is a top-level destination outside the linear
  // pipeline. Toggling returns to whichever stage the user came from.
  const lastStageRef = useRef<string>("results");
  const toggleFhirServer = () => {
    setActiveStage((cur) => {
      if (cur === "fhir-server") return lastStageRef.current;
      lastStageRef.current = cur;
      return "fhir-server";
    });
  };

  const configHint = config
    ? `${config.match.source || "—"} · ${config.emit.length} emit rule${
        config.emit.length === 1 ? "" : "s"
      }`
    : adapterLoading
    ? "Loading…"
    : undefined;

  return (
    <div className="app">
      <Topbar
        onRun={() => handleRun(scanPhase ? { preserveConcepts: true } : undefined)}
        running={running}
        canRun={canRun}
        configKey={configKey}
        setConfigKey={setConfigKey}
        configIds={configIds}
        configHint={configHint}
        batchProgress={batchProgress}
        onCancel={cancelBatch}
        scanPhase={scanPhase}
        onOpenFhirServer={toggleFhirServer}
        fhirServerActive={activeStage === "fhir-server"}
      />
      <StageStrip stages={stageDefs} active={activeStage} onJump={setActiveStage} />

      <div className="main">
        {runError && (
          <div className="qflag err" style={{ marginBottom: 18 }}>
            <div className="qf-bar" />
            <div>
              <div className="qf-code">RUN_FAILED</div>
              <div className="qf-msg">{runError}</div>
            </div>
          </div>
        )}

        {activeStage === "connector" && (
          <ConnectorPanel
            customText={customText}
            setCustomText={setCustomText}
            customFormat={customFormat}
            setCustomFormat={setCustomFormat}
            customSource={customSource}
            setCustomSource={setCustomSource}
            customError={customError}
          />
        )}

        {activeStage === "adapter" && (
          <AdapterPanel
            config={config}
            onChange={setConfig}
            configKey={configKey}
            setConfigKey={setConfigKey}
            inputData={inputData}
            source={sourceName}
            onLLMResult={onLLMResult}
            descriptors={descriptorMap[configKey] ?? []}
            loading={adapterLoading}
            loadError={adapterError}
            matches={configMatches}
          />
        )}

        {activeStage === "results" && (
          <ResultsPanel
            events={events}
            source={eventSource}
            bundle={bundle}
            omopCdm={omopCdm}
            conceptSlots={conceptSlots}
            conceptMappings={conceptMappings}
            onConceptChange={handleConceptChange}
            onBulkConceptChange={handleBulkConceptChange}
            conceptNoMatches={conceptNoMatches}
            onNoMatchesChange={handleNoMatchesChange}
            onRerunWithConcepts={() => handleRun({ preserveConcepts: true })}
            rerunning={running}
            adapterDiagnostics={adapterDiagnostics}
            yamlText={yamlText}
            inputData={inputData}
            onApplyYaml={applyPatchedYaml}
            scanPhase={scanPhase}
            onOpenServer={toggleFhirServer}
          />
        )}

        {activeStage === "fhir-server" && <FhirServerPanel />}

        {activeStage !== "fhir-server" && (
          <PipelineNav activeStage={activeStage} onJump={setActiveStage} />
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";

import AdapterPanel from "@/components/adapter/AdapterPanel";
import ConnectorPanel, { type InputMode } from "@/components/connector/ConnectorPanel";
import PipelineNav from "@/components/PipelineNav";
import ResultsPanel from "@/components/results/ResultsPanel";
import StageRulesPanel from "@/components/StageRulesPanel";
import StageStrip, { type StageDef } from "@/components/StageStrip";
import Topbar from "@/components/Topbar";
import {
  getConfig,
  listConfigs,
  matchConfigs,
  transform,
  type ConfigMatch,
  type TransformFormat,
  type TransformResponse,
} from "@/lib/api";
import { summarizeClean, summarizeQualify, summarizeValidate } from "@/lib/rules";
import { SAMPLE_CONFIGS, SAMPLE_DATASETS, SIMULATED_EVENTS } from "@/lib/sampleData";
import type { AdapterConfig, CanonicalEvent, Coding } from "@/lib/types";
import { dumpAdapterYaml, parseAdapterYaml } from "@/lib/yaml";

const SAMPLE_CONFIG_KEYS = Object.keys(SAMPLE_CONFIGS);

const SAMPLE_RAW = { value: " 244 ", unit: null, timestamp: "2025-01-12T06:04:00Z", category: "heart-rate" };
const SAMPLE_CLEANED = { value: 244, unit: "bpm", timestamp: "2025-01-12T06:04:00.000Z", category: "heart-rate" };
const SAMPLE_VALIDATED = { ...SAMPLE_CLEANED, _flags: ["HR_OUT_OF_RANGE"] };
const SAMPLE_QUALIFIED = {
  ...SAMPLE_CLEANED,
  plausibility: "review",
  completeness: 1.0,
};

export default function Page() {
  // Connector state
  const [inputMode, setInputMode] = useState<InputMode>("sample");
  const [datasetKey, setDatasetKey] = useState<string>(Object.keys(SAMPLE_DATASETS)[0]);
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

  // Stage navigation
  const [activeStage, setActiveStage] = useState<string>("connector");

  // When the user clicks "Edit in YAML →" inside a StageRulesPanel we hop to
  // the adapter stage and ask it to start in YAML mode.
  const [adapterYamlIntent, setAdapterYamlIntent] = useState(0);

  // Run state
  const [runResult, setRunResult] = useState<TransformResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // Concept-mapping state (session-only, sent on each /api/transform call).
  const [conceptMappings, setConceptMappings] = useState<Record<string, Coding>>({});

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

  const onLLMResult = (yamlText: string, configId: string) => {
    try {
      const parsed = parseAdapterYaml(yamlText);
      setConfigMap((m) => ({ ...m, [configId]: parsed }));
      setBackendIds((ids) => (ids.includes(configId) ? ids : [...ids, configId]));
      setConfigKey(configId);
    } catch (e) {
      setAdapterError((e as Error).message);
    }
  };

  // The active payload format. Sample datasets are always JSON.
  const activeFormat: TransformFormat = inputMode === "sample" ? "json" : customFormat;

  // ── Resolve the input data for transform.
  // For JSON: parsed object/array. For CSV: raw text passed through to the backend.
  // Reads from the debounced text so a paste of multi-MB JSON doesn't re-parse
  // on every keystroke.
  const inputData: unknown | null = useMemo(() => {
    if (inputMode === "sample") {
      return SAMPLE_DATASETS[datasetKey]?.record ?? null;
    }
    if (!debouncedCustomText.trim()) return null;
    if (customFormat === "csv") return debouncedCustomText;
    try {
      return JSON.parse(debouncedCustomText) as unknown;
    } catch {
      return null;
    }
  }, [inputMode, datasetKey, debouncedCustomText, customFormat]);

  // String form of inputData for endpoints that parse server-side (e.g.
  // /configs/match). For custom input we already have the raw text — skip
  // re-stringifying the parsed JSON (a wasted full pass on large payloads).
  const inputDataString: string | null = useMemo(() => {
    if (inputMode === "custom") {
      return debouncedCustomText.trim() ? debouncedCustomText : null;
    }
    if (inputData == null) return null;
    if (typeof inputData === "string") return inputData;
    return JSON.stringify(inputData);
  }, [inputMode, debouncedCustomText, inputData]);

  // Validate custom payload for user feedback (non-blocking). Reads from the
  // debounced text so we don't JSON.parse a multi-MB blob on each keystroke.
  useEffect(() => {
    if (inputMode !== "custom" || !debouncedCustomText.trim()) {
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
  }, [debouncedCustomText, inputMode, customFormat]);

  // Source name describes the *data*, not the adapter. In sample mode it comes
  // from the fixture; in custom mode the user owns it. Don't fall back to the
  // currently-selected adapter's source — that's how an unrelated adapter's
  // `match.source` (e.g. "app-usage") leaks into transform requests and into
  // LLM-generated configs for other data.
  const sourceName = useMemo(() => {
    if (inputMode === "sample") return SAMPLE_DATASETS[datasetKey]?.source ?? "";
    return customSource.trim();
  }, [inputMode, datasetKey, customSource]);

  // ── Ask the backend which registered configs apply to the current input.
  // Debounced so paste/keystroke streams don't spam the endpoint. Failures
  // hide the panel rather than surface noise — same forgiving pattern as
  // listConfigs above.
  useEffect(() => {
    if (inputDataString == null) {
      setConfigMatches(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      matchConfigs(inputDataString, activeFormat, sourceName || undefined)
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
  }, [inputDataString, activeFormat, sourceName]);

  const events: CanonicalEvent[] = runResult?.events ?? SIMULATED_EVENTS;
  const eventSource: "live" | "simulated" = runResult ? "live" : "simulated";
  const bundle = runResult?.bundle ?? null;
  const conceptSlots = runResult?.concept_slots ?? [];

  const cleanSummary = useMemo(() => summarizeClean(config), [config]);
  const validateSummary = useMemo(() => summarizeValidate(config), [config]);
  const qualifySummary = useMemo(() => summarizeQualify(config), [config]);

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
    const cleanOn = cleanSummary.filter((r) => r.enabled).length;
    const validateOn = validateSummary.filter((r) => r.enabled).length;
    const qualifyOn = qualifySummary.filter((r) => r.enabled).length;
    // Strip stays at 5 stages to match the CSS grid (Results is reached via prev/next nav).
    return [
      {
        id: "connector",
        label: "Connector",
        count: 1,
        note: "1 record · sample",
        done: activeStage !== "connector",
        pulse: activeStage === "connector",
      },
      {
        id: "adapter",
        label: "Adapter",
        count: total,
        note: `${emitCount} emit rules`,
        done: ["cleaning", "validation", "qualification", "results"].includes(activeStage),
        pulse: activeStage === "adapter",
      },
      {
        id: "cleaning",
        label: "Cleaner",
        count: total,
        note: `${cleanOn}/${cleanSummary.length} rules on`,
        done: ["validation", "qualification", "results"].includes(activeStage),
        pulse: activeStage === "cleaning",
      },
      {
        id: "validation",
        label: "Validator",
        count: total,
        note: `${validateOn}/${validateSummary.length} rules on`,
        warn,
        done: ["qualification", "results"].includes(activeStage),
        pulse: activeStage === "validation",
      },
      {
        id: "qualification",
        label: "Qualifier",
        count: total,
        note: `${qualifyOn}/${qualifySummary.length} rules on`,
        warn,
        err,
        done: activeStage === "results",
        pulse: activeStage === "qualification",
      },
    ];
  }, [events, flagTotals, activeStage, config, cleanSummary, validateSummary, qualifySummary]);

  const canRun = inputData != null && config != null;

  async function handleRun(opts?: { preserveConcepts?: boolean }) {
    if (!canRun || !config) {
      setRunError("Need both input data and an adapter config before running.");
      return;
    }
    setRunError(null);
    setRunning(true);
    try {
      const yamlText = dumpAdapterYaml(config);
      const mappingsToSend = opts?.preserveConcepts ? conceptMappings : {};
      // Fresh runs (from Topbar) clear stale picks so slots reflect the new
      // dataset; re-runs from the Concepts tab keep the current picks.
      if (!opts?.preserveConcepts) {
        setConceptMappings({});
      }
      const res = await transform({
        data: inputData,
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

  const configIds = useMemo(() => {
    const merged = new Set<string>([...SAMPLE_CONFIG_KEYS, ...backendIds]);
    return Array.from(merged);
  }, [backendIds]);

  // Hop the user to the YAML editor on the adapter stage with a fresh intent
  // counter so AdapterPanel re-mounts in YAML mode every time.
  const editYaml = () => {
    setAdapterYamlIntent((n) => n + 1);
    setActiveStage("adapter");
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
        onRun={() => handleRun()}
        running={running}
        canRun={canRun}
        configKey={configKey}
        setConfigKey={setConfigKey}
        configIds={configIds}
        configHint={configHint}
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
            mode={inputMode}
            setMode={setInputMode}
            datasetKey={datasetKey}
            setDatasetKey={setDatasetKey}
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
            key={`adapter-${adapterYamlIntent}`}
            config={config}
            onChange={setConfig}
            configKey={configKey}
            setConfigKey={setConfigKey}
            inputData={inputData}
            source={sourceName}
            onLLMResult={onLLMResult}
            loading={adapterLoading}
            loadError={adapterError}
            matches={configMatches}
            initialYamlMode={adapterYamlIntent > 0}
          />
        )}

        {activeStage === "cleaning" && (
          <StageRulesPanel
            title="Cleaner"
            eyebrow="Stage 03 · Heuristic cleaning"
            blurb="Whitespace strip → Timestamp normalize → Type coerce → Unit infer. Each heuristic mutates the event in place; fail-soft, no flags raised. Stage advances to CLEANED."
            summary={cleanSummary}
            sectionKey="clean"
            onEditYaml={editYaml}
            sample={SAMPLE_RAW}
            sampleAfter={SAMPLE_CLEANED}
          />
        )}

        {activeStage === "validation" && (
          <StageRulesPanel
            title="Validator"
            eyebrow="Stage 04 · Assertions only"
            blurb="Validators ASSERT — they never mutate. Each returns a list of QualityFlags; the runner appends and de-dups against adapter-declared flags. Failed validation events are tagged, not dropped."
            summary={validateSummary}
            sectionKey="validate"
            onEditYaml={editYaml}
            sample={SAMPLE_CLEANED}
            sampleAfter={SAMPLE_VALIDATED}
            sampleFlags={[
              {
                code: "HR_OUT_OF_RANGE",
                severity: "warning",
                stage: "validated",
                message: "value 244 outside [25, 230] for heart-rate",
              },
            ]}
          />
        )}

        {activeStage === "qualification" && (
          <StageRulesPanel
            title="Qualifier"
            eyebrow="Stage 05 · Cross-event quality"
            blurb="Operates over the request's events as a batch. Computes completeness, fingerprints duplicates, and runs Hampel outlier (median ± 3.5·MAD per (subject_id, category), min n=5). Derives conformance + plausibility."
            summary={qualifySummary}
            sectionKey="qualify"
            onEditYaml={editYaml}
            sample={SAMPLE_VALIDATED}
            sampleAfter={SAMPLE_QUALIFIED}
            sampleFlags={[
              {
                code: "HAMPEL_OUTLIER",
                severity: "warning",
                stage: "qualified",
                message: "Hampel: |x − median| > 3.5·MAD for (u-08431, heart-rate)",
              },
            ]}
          />
        )}

        {activeStage === "results" && (
          <ResultsPanel
            events={events}
            source={eventSource}
            bundle={bundle}
            conceptSlots={conceptSlots}
            conceptMappings={conceptMappings}
            onConceptChange={handleConceptChange}
            onRerunWithConcepts={() => handleRun({ preserveConcepts: true })}
            rerunning={running}
          />
        )}

        <PipelineNav activeStage={activeStage} onJump={setActiveStage} />
      </div>
    </div>
  );
}

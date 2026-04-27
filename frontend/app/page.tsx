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
  transform,
  type TransformFormat,
  type TransformResponse,
} from "@/lib/api";
import { CLEANER_RULES, QUALIFIER_RULES, VALIDATOR_RULES } from "@/lib/rules";
import { SAMPLE_CONFIGS, SAMPLE_DATASETS, SIMULATED_EVENTS } from "@/lib/sampleData";
import type { AdapterConfig, CanonicalEvent } from "@/lib/types";
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
  const [customFormat, setCustomFormat] = useState<TransformFormat>("json");
  const [customSource, setCustomSource] = useState<string>("");
  const [customError, setCustomError] = useState<string | null>(null);

  // Adapter state — backend configs override the seeded SAMPLE_CONFIGS where available.
  const [configMap, setConfigMap] = useState<Record<string, AdapterConfig>>({ ...SAMPLE_CONFIGS });
  const [configKey, setConfigKey] = useState<string>(SAMPLE_CONFIG_KEYS[0] ?? "");
  const [backendIds, setBackendIds] = useState<string[]>([]);
  const [adapterLoading, setAdapterLoading] = useState(false);
  const [adapterError, setAdapterError] = useState<string | null>(null);

  // Stage navigation
  const [activeStage, setActiveStage] = useState<string>("connector");

  // Rule visualization (per-stage toggles — currently cosmetic)
  const [cleanerRules, setCleanerRules] = useState(CLEANER_RULES);
  const [validatorRules, setValidatorRules] = useState(VALIDATOR_RULES);
  const [qualifierRules, setQualifierRules] = useState(QUALIFIER_RULES);

  // Run state
  const [runResult, setRunResult] = useState<TransformResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

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
  const inputData: unknown | null = useMemo(() => {
    if (inputMode === "sample") {
      return SAMPLE_DATASETS[datasetKey]?.record ?? null;
    }
    if (!customText.trim()) return null;
    if (customFormat === "csv") return customText;
    try {
      return JSON.parse(customText) as unknown;
    } catch {
      return null;
    }
  }, [inputMode, datasetKey, customText, customFormat]);

  // Validate custom payload for user feedback (non-blocking).
  useEffect(() => {
    if (inputMode !== "custom" || !customText.trim()) {
      setCustomError(null);
      return;
    }
    if (customFormat === "csv") {
      // Minimal sanity check: at least one newline-separated row of fields.
      const firstLine = customText.split(/\r?\n/, 1)[0] ?? "";
      if (!firstLine.includes(",")) {
        setCustomError("CSV looks malformed: no comma found in the header row.");
      } else {
        setCustomError(null);
      }
      return;
    }
    try {
      JSON.parse(customText);
      setCustomError(null);
    } catch (e) {
      setCustomError(`Invalid JSON: ${(e as Error).message}`);
    }
  }, [customText, inputMode, customFormat]);

  // Source name describes the *data*, not the adapter. In sample mode it comes
  // from the fixture; in custom mode the user owns it. Don't fall back to the
  // currently-selected adapter's source — that's how an unrelated adapter's
  // `match.source` (e.g. "app-usage") leaks into transform requests and into
  // LLM-generated configs for other data.
  const sourceName = useMemo(() => {
    if (inputMode === "sample") return SAMPLE_DATASETS[datasetKey]?.source ?? "";
    return customSource.trim();
  }, [inputMode, datasetKey, customSource]);

  const events: CanonicalEvent[] = runResult?.events ?? SIMULATED_EVENTS;
  const eventSource: "live" | "simulated" = runResult ? "live" : "simulated";

  const stageDefs: StageDef[] = useMemo(() => {
    const total = events.length;
    const warn = events.reduce(
      (s, e) => s + e.quality.flags.filter((f) => f.severity === "warning").length,
      0,
    );
    const err = events.reduce(
      (s, e) => s + e.quality.flags.filter((f) => f.severity === "error").length,
      0,
    );
    const emitCount = config?.emit.length ?? 0;
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
        note: `${cleanerRules.filter((r) => r.on).length}/${cleanerRules.length} rules on`,
        done: ["validation", "qualification", "results"].includes(activeStage),
        pulse: activeStage === "cleaning",
      },
      {
        id: "validation",
        label: "Validator",
        count: total,
        note: `${validatorRules.filter((r) => r.on).length}/${validatorRules.length} rules on`,
        warn,
        done: ["qualification", "results"].includes(activeStage),
        pulse: activeStage === "validation",
      },
      {
        id: "qualification",
        label: "Qualifier",
        count: total,
        note: `${qualifierRules.filter((r) => r.on).length}/${qualifierRules.length} rules on`,
        warn,
        err,
        done: activeStage === "results",
        pulse: activeStage === "qualification",
      },
    ];
  }, [events, activeStage, config, cleanerRules, validatorRules, qualifierRules]);

  const canRun = inputData != null && config != null;

  async function handleRun() {
    if (!canRun || !config) {
      setRunError("Need both input data and an adapter config before running.");
      return;
    }
    setRunError(null);
    setRunning(true);
    try {
      const yamlText = dumpAdapterYaml(config);
      const res = await transform({
        data: inputData,
        yaml: yamlText,
        source: sourceName || undefined,
        format: activeFormat,
      });
      setRunResult(res);
      setActiveStage("results");
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const configIds = useMemo(() => {
    const merged = new Set<string>([...SAMPLE_CONFIG_KEYS, ...backendIds]);
    return Array.from(merged);
  }, [backendIds]);

  return (
    <div className="app">
      <Topbar onRun={handleRun} running={running} canRun={canRun} />
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
            config={config}
            onChange={setConfig}
            configKey={configKey}
            setConfigKey={setConfigKey}
            configIds={configIds}
            inputData={inputData}
            source={sourceName}
            onLLMResult={onLLMResult}
            loading={adapterLoading}
            loadError={adapterError}
          />
        )}

        {activeStage === "cleaning" && (
          <StageRulesPanel
            title="Cleaner"
            eyebrow="Stage 03 · Heuristic cleaning"
            blurb="Whitespace strip → Timestamp normalize → Type coerce → Unit infer. Each heuristic mutates the event in place; fail-soft, no flags raised. Stage advances to CLEANED."
            rules={cleanerRules}
            setRules={setCleanerRules}
            sample={SAMPLE_RAW}
            sampleAfter={SAMPLE_CLEANED}
          />
        )}

        {activeStage === "validation" && (
          <StageRulesPanel
            title="Validator"
            eyebrow="Stage 04 · Assertions only"
            blurb="Validators ASSERT — they never mutate. Each returns a list of QualityFlags; the runner appends and de-dups against adapter-declared flags. Failed validation events are tagged, not dropped."
            rules={validatorRules}
            setRules={setValidatorRules}
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
            rules={qualifierRules}
            setRules={setQualifierRules}
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
          <ResultsPanel events={events} source={eventSource} />
        )}

        <PipelineNav activeStage={activeStage} onJump={setActiveStage} />
      </div>
    </div>
  );
}

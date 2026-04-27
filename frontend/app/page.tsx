"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ConfigBrowser from "@/components/ConfigBrowser";
import DataInput from "@/components/DataInput";
import ResultsPanel from "@/components/ResultsPanel";
import YamlEditor, { type SaveStatus } from "@/components/YamlEditor";
import {
  generateConfig,
  getConfig,
  transform,
  updateConfig,
  type TransformResponse,
} from "@/lib/api";

type Mode = "generate" | "existing";

const AUTOSAVE_DEBOUNCE_MS = 600;

export default function Page() {
  const [data, setData] = useState<unknown | null>(null);
  const [description, setDescription] = useState("");
  const [hints, setHints] = useState("");
  const [source, setSource] = useState("");

  const [mode, setMode] = useState<Mode>("generate");
  const [yaml, setYaml] = useState("");
  const [configId, setConfigId] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [browserRefresh, setBrowserRefresh] = useState(0);

  const [result, setResult] = useState<TransformResponse | null>(null);

  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // Autosave: debounce PUT when yaml changes and configId is set.
  const yamlRef = useRef(yaml);
  const configIdRef = useRef(configId);
  const lastSavedRef = useRef<string>("");
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    yamlRef.current = yaml;
  }, [yaml]);

  useEffect(() => {
    configIdRef.current = configId;
  }, [configId]);

  const flushSave = useCallback(async () => {
    const id = configIdRef.current;
    const current = yamlRef.current;
    if (!id) return;
    if (current === lastSavedRef.current) return;
    setSaveStatus("saving");
    setSaveError(null);
    try {
      const saved = await updateConfig(id, current);
      lastSavedRef.current = saved.yaml;
      if (yamlRef.current === saved.yaml) {
        setSaveStatus("saved");
      } else {
        // User typed while we were saving — keep dirty and schedule another save.
        setSaveStatus("dirty");
        scheduleSave();
      }
    } catch (e) {
      setSaveStatus("error");
      setSaveError((e as Error).message);
    }
  }, []);

  const scheduleSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      void flushSave();
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [flushSave]);

  function handleYamlChange(next: string) {
    setYaml(next);
    if (configId && next !== lastSavedRef.current) {
      setSaveStatus("dirty");
      scheduleSave();
    }
  }

  async function handleGenerate() {
    if (!data) {
      setGenerateError("Load some data first.");
      return;
    }
    if (!description.trim()) {
      setGenerateError("Add a description so the LLM knows what this data is.");
      return;
    }
    setGenerateError(null);
    setGenerating(true);
    try {
      const res = await generateConfig({
        data,
        description,
        hints: hints || undefined,
        source: source || undefined,
      });
      setYaml(res.yaml);
      setConfigId(res.id);
      lastSavedRef.current = res.yaml;
      setSaveStatus("saved");
      setSaveError(null);
      setBrowserRefresh((n) => n + 1);
    } catch (e) {
      setGenerateError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSelectExisting(id: string) {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    try {
      const cfg = await getConfig(id);
      setYaml(cfg.yaml);
      setConfigId(cfg.id);
      lastSavedRef.current = cfg.yaml;
      setSaveStatus("saved");
      setSaveError(null);
    } catch (e) {
      setSaveStatus("error");
      setSaveError((e as Error).message);
    }
  }

  async function handleRun() {
    if (!data) {
      setRunError("Load some data first.");
      return;
    }
    if (!yaml.trim()) {
      setRunError("Generate or select a YAML config first.");
      return;
    }
    // Make sure the latest edits are on the server before running.
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
      await flushSave();
    }
    setRunError(null);
    setRunning(true);
    try {
      const res = await transform({
        data,
        yaml,
        source: source || undefined,
      });
      setResult(res);
    } catch (e) {
      setRunError((e as Error).message);
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <header>
        <h1 className="text-2xl font-bold">Progressive Harmonization ETL</h1>
        <p className="text-sm text-gray-600">
          Upload source data, then either generate a new YAML config via the
          LLM or pick an existing one. Edits are persisted automatically.
        </p>
      </header>

      <DataInput data={data} onChange={setData} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">2. Source (optional)</h2>
        <label className="block text-sm font-medium">Source name</label>
        <input
          type="text"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="e.g. withings, linguistic-games"
          className="w-full rounded border p-2 text-sm"
        />
        <p className="text-xs text-gray-500">
          Used to filter matching configs and to stamp transformed events. Can
          be left blank while browsing.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">3. Choose a config</h2>
        <div className="flex gap-2 border-b">
          {(["generate", "existing"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 text-sm ${
                mode === m ? "border-b-2 border-black font-medium" : "text-gray-500"
              }`}
            >
              {m === "generate" ? "Generate new" : "Use existing"}
            </button>
          ))}
        </div>

        {mode === "generate" ? (
          <div className="space-y-3">
            <label className="block text-sm font-medium">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="What does each record represent? Which field identifies the subject? Any quirks (missing timestamps, embedded arrays, sentinels)?"
              className="w-full rounded border p-2 text-sm"
            />
            <label className="block text-sm font-medium">Extra hints (optional)</label>
            <textarea
              value={hints}
              onChange={(e) => setHints(e.target.value)}
              rows={2}
              placeholder="e.g. 'the score field is the best-play score, not cumulative'"
              className="w-full rounded border p-2 text-sm"
            />
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {generating ? "Generating…" : "Generate config"}
            </button>
            {generateError && (
              <p className="rounded bg-red-50 p-2 text-sm text-red-700">
                {generateError}
              </p>
            )}
          </div>
        ) : (
          <ConfigBrowser
            data={data}
            source={source}
            selectedId={configId}
            onSelect={handleSelectExisting}
            refreshKey={browserRefresh}
          />
        )}
      </section>

      {yaml && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">
            4. Review / edit YAML
            {configId && (
              <span className="ml-2 font-mono text-sm text-gray-500">
                ({configId})
              </span>
            )}
          </h2>
          <YamlEditor
            value={yaml}
            onChange={handleYamlChange}
            status={saveStatus}
            statusMessage={saveError ?? undefined}
          />
          <button
            onClick={handleRun}
            disabled={running}
            className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {running ? "Running…" : "Run transformation"}
          </button>
          {runError && (
            <p className="rounded bg-red-50 p-2 text-sm text-red-700">
              {runError}
            </p>
          )}
        </section>
      )}

      <ResultsPanel result={result} yaml={yaml} />
    </main>
  );
}

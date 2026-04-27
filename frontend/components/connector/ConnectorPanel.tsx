"use client";

import { useRef, useState } from "react";

import { cx } from "@/lib/cx";
import { SAMPLE_DATASETS } from "@/lib/sampleData";
import type { TransformFormat } from "@/lib/api";

export type InputMode = "sample" | "custom";

interface Props {
  mode: InputMode;
  setMode: (m: InputMode) => void;
  datasetKey: string;
  setDatasetKey: (k: string) => void;
  customText: string;
  setCustomText: (s: string) => void;
  customFormat: TransformFormat;
  setCustomFormat: (f: TransformFormat) => void;
  customSource: string;
  setCustomSource: (s: string) => void;
  customError: string | null;
}

function formatFromFilename(name: string): TransformFormat | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".json")) return "json";
  return null;
}

export default function ConnectorPanel({
  mode,
  setMode,
  datasetKey,
  setDatasetKey,
  customText,
  setCustomText,
  customFormat,
  setCustomFormat,
  customSource,
  setCustomSource,
  customError,
}: Props) {
  const ds = SAMPLE_DATASETS[datasetKey];
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [drag, setDrag] = useState(false);

  const handleFile = (file: File) => {
    const fmt = formatFromFilename(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") {
        setCustomText(result);
        if (fmt) setCustomFormat(fmt);
        setMode("custom");
      }
    };
    reader.readAsText(file);
  };

  return (
    <div>
      <div className="section-sub">Stage 01 · Source ingest</div>
      <h2 className="section-title">Connector</h2>
      <p className="muted" style={{ maxWidth: 640, marginTop: 0 }}>
        The pipeline begins by reading raw records. The connector annotates each with metadata
        (<span className="mono">source</span>, format) and hands them to the registry to find a matching adapter.
        JSON and CSV are supported today.
      </p>

      <div className="two-pane" style={{ marginTop: 24 }}>
        <div className="card">
          <div className="card-head">
            <span className="eyebrow">Input source</span>
            <div className="seg">
              <button className={mode === "sample" ? "on" : ""} onClick={() => setMode("sample")}>
                Sample
              </button>
              <button className={mode === "custom" ? "on" : ""} onClick={() => setMode("custom")}>
                Custom
              </button>
            </div>
          </div>
          <div className="card-body">
            {mode === "sample" ? (
              <>
                <div className="field">
                  <label>Sample dataset</label>
                  <select
                    className="select"
                    value={datasetKey}
                    onChange={(e) => setDatasetKey(e.target.value)}
                  >
                    {Object.entries(SAMPLE_DATASETS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="spacer-sm" />
                <div className="field">
                  <label>Source file</label>
                  <div className="chip mono" style={{ alignSelf: "flex-start" }}>
                    {ds.file}
                  </div>
                </div>
                <div className="spacer-sm" />
                <div className="field">
                  <label>Detected source name</label>
                  <div>
                    <span className="chip accent">{ds.source}</span>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div
                  className={cx("dropzone", drag && "dragover")}
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    const f = e.dataTransfer.files?.[0];
                    if (f) handleFile(f);
                  }}
                >
                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    Drop a JSON or CSV file or click to browse
                  </div>
                  <div className="help">.json · .csv · single record, array, or table</div>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="application/json,.json,text/csv,.csv"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFile(f);
                    }}
                    style={{ display: "none" }}
                  />
                </div>
                <div className="spacer-md" />
                <div className="row">
                  <div className="field" style={{ flex: 0 }}>
                    <label>Format</label>
                    <div className="seg" style={{ alignSelf: "flex-start" }}>
                      <button
                        className={customFormat === "json" ? "on" : ""}
                        onClick={() => setCustomFormat("json")}
                      >
                        JSON
                      </button>
                      <button
                        className={customFormat === "csv" ? "on" : ""}
                        onClick={() => setCustomFormat("csv")}
                      >
                        CSV
                      </button>
                    </div>
                  </div>
                  <div className="field">
                    <label>Source name</label>
                    <input
                      className="input mono"
                      value={customSource}
                      placeholder="e.g. fitbit, withings, fitabase"
                      onChange={(e) => setCustomSource(e.target.value)}
                    />
                  </div>
                </div>
                <div className="help">
                  Source name is sent to the backend as the record&apos;s <span className="mono">_metadata.source</span> and is what the adapter&apos;s <span className="mono">match.source</span> compares against. Set this before generating an adapter config so the LLM knows what to write.
                </div>
                <div className="spacer-sm" />
                <div className="field">
                  <label>{customFormat === "csv" ? "Or paste CSV" : "Or paste JSON"}</label>
                  <textarea
                    className="textarea mono"
                    rows={8}
                    placeholder={
                      customFormat === "csv"
                        ? "Id,ActivityDate,TotalSteps\n1503960366,4/12/2016,13162\n…"
                        : '{ "userId": "u-...", ... }'
                    }
                    value={customText}
                    onChange={(e) => setCustomText(e.target.value)}
                  />
                  {customError && (
                    <p className="help" style={{ color: "var(--err)" }}>
                      {customError}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="eyebrow">Record preview</span>
            <span className="chip">{mode === "custom" ? customFormat : "sample"}</span>
          </div>
          <div className="card-body">
            <pre className="code-pre">
              {mode === "custom"
                ? customText || "// paste or drop a file to preview"
                : JSON.stringify(ds.record, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

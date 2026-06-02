"use client";

import { useMemo, useRef, useState } from "react";

import { cx } from "@/lib/cx";
import type { TransformFormat } from "@/lib/api";

export type InputMode = "custom";

const PREVIEW_MAX = 1_000;

interface Props {
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
  customText,
  setCustomText,
  customFormat,
  setCustomFormat,
  customSource,
  setCustomSource,
  customError,
}: Props) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [drag, setDrag] = useState(false);

  const previewText = useMemo(() => {
    if (!customText) return "// paste or drop a file to preview";
    if (customText.length <= PREVIEW_MAX) return customText;
    return customText.slice(0, PREVIEW_MAX) + "\n…";
  }, [customText]);

  const previewTruncated = customText.length > PREVIEW_MAX;

  const handleFile = (file: File) => {
    const fmt = formatFromFilename(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") {
        setCustomText(result);
        if (fmt) setCustomFormat(fmt);
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
          </div>
          <div className="card-body">
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

            <div className="spacer-sm" />
            <div className="field">
              <label>Source name</label>
              <input
                className="input mono"
                value={customSource}
                placeholder="e.g. fitbit"
                onChange={(e) => setCustomSource(e.target.value)}
              />
            </div>
            <div className="help">
              Source name is sent to the backend as the record&apos;s <span className="mono">_metadata.source</span> and is what the adapter&apos;s <span className="mono">match.source</span> compares against. Set this before generating an adapter config so the LLM knows what to write.
            </div>

            {customError && (
              <div className="qflag err" style={{ marginTop: 12 }}>
                <div className="qf-bar" />
                <div>
                  <div className="qf-code">INPUT_ERROR</div>
                  <div className="qf-msg">{customError}</div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="eyebrow">Record preview</span>
            <span className="chip">{customFormat}</span>
          </div>
          <div className="card-body">
            <pre className="code-pre">{previewText}</pre>
            {previewTruncated && (
              <p className="help" style={{ marginTop: 8 }}>
                Showing first {PREVIEW_MAX.toLocaleString()} of{" "}
                {customText.length.toLocaleString()} characters · full content sent to backend on Run.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

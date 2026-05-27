"use client";

import type { BatchProgress } from "@/lib/batch";

interface Props {
  onRun: () => void;
  running: boolean;
  canRun: boolean;
  configKey: string;
  setConfigKey: (k: string) => void;
  configIds: string[];
  /** Optional helper text under the picker (e.g. "fitbit · 3 emit rules"). */
  configHint?: string;
  batchProgress?: BatchProgress | null;
  onCancel?: () => void;
  scanPhase?: boolean;
}

export default function Topbar({
  onRun,
  running,
  canRun,
  configKey,
  setConfigKey,
  configIds,
  configHint,
  batchProgress,
  onCancel,
  scanPhase,
}: Props) {
  const isBatched = batchProgress != null && batchProgress.batchCount > 1;
  return (
    <div className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <span className="brand-name">Harmonia</span>
        <span className="brand-sub">progressive harmonization · v0.4</span>
      </div>
      <div className="topbar-spacer" />

      <div
        className="field"
        style={{ minWidth: 280, marginRight: 12, marginBottom: 0 }}
        title="One config governs every pipeline stage — adapter, cleaner, validator, qualifier"
      >
        <label style={{ fontSize: 11, opacity: 0.75 }}>Pipeline config</label>
        <select
          className="select"
          value={configKey}
          onChange={(e) => setConfigKey(e.target.value)}
          disabled={configIds.length === 0}
        >
          {configIds.length === 0 && <option value="">No configs available</option>}
          {configIds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        {configHint && (
          <div className="help" style={{ marginTop: 2, fontSize: 11 }}>
            {configHint}
          </div>
        )}
      </div>

      <div className="chip mono">POST /api/transform</div>

      {isBatched && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 8 }}>
          <div style={{ minWidth: 180 }}>
            <div style={{ fontSize: 12, opacity: 0.85, whiteSpace: "nowrap" }}>
              Batch {batchProgress.batchIndex + 1}/{batchProgress.batchCount}
              {batchProgress.eventsProcessed > 0 && (
                <span style={{ opacity: 0.6 }}> · {batchProgress.eventsProcessed.toLocaleString()} events</span>
              )}
            </div>
            <div
              style={{
                height: 3,
                borderRadius: 2,
                background: "var(--surface-2, #333)",
                marginTop: 3,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  borderRadius: 2,
                  width: `${Math.round(((batchProgress.batchIndex + (batchProgress.status === "running" ? 0.5 : 1)) / batchProgress.batchCount) * 100)}%`,
                  background: batchProgress.status === "error" ? "var(--err, #e55)" : "var(--accent, #5af)",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>
          {onCancel && batchProgress.status === "running" && (
            <button
              className="btn"
              onClick={onCancel}
              style={{ fontSize: 12, padding: "3px 10px" }}
            >
              Cancel
            </button>
          )}
        </div>
      )}

      <button
        className="btn primary"
        onClick={onRun}
        disabled={running || !canRun}
        title={canRun ? (scanPhase ? "Transform the full dataset with mapped concepts" : "Run the pipeline") : "Load data and select a config first"}
      >
        {running ? (
          <>
            <span className="spin" />
            {isBatched ? "Batching…" : scanPhase ? "Scanning…" : "Running…"}
          </>
        ) : scanPhase ? (
          <>Transform all →</>
        ) : (
          <>Run pipeline →</>
        )}
      </button>
    </div>
  );
}

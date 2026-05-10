"use client";

interface Props {
  onRun: () => void;
  running: boolean;
  canRun: boolean;
  configKey: string;
  setConfigKey: (k: string) => void;
  configIds: string[];
  /** Optional helper text under the picker (e.g. "fitbit · 3 emit rules"). */
  configHint?: string;
}

export default function Topbar({
  onRun,
  running,
  canRun,
  configKey,
  setConfigKey,
  configIds,
  configHint,
}: Props) {
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
      <button
        className="btn primary"
        onClick={onRun}
        disabled={running || !canRun}
        title={canRun ? "Run the pipeline" : "Load data and select a config first"}
      >
        {running ? (
          <>
            <span className="spin" />
            Running…
          </>
        ) : (
          <>Run pipeline →</>
        )}
      </button>
    </div>
  );
}

"use client";

interface Props {
  onRun: () => void;
  running: boolean;
  canRun: boolean;
}

export default function Topbar({ onRun, running, canRun }: Props) {
  return (
    <div className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <span className="brand-name">Harmonia</span>
        <span className="brand-sub">progressive harmonization · v0.4</span>
      </div>
      <div className="topbar-spacer" />
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

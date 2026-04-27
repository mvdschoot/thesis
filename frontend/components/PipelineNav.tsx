"use client";

const STAGE_ORDER = ["connector", "adapter", "cleaning", "validation", "qualification", "results"] as const;

const LABEL: Record<(typeof STAGE_ORDER)[number], string> = {
  connector: "Connector",
  adapter: "Adapter",
  cleaning: "Cleaner",
  validation: "Validator",
  qualification: "Qualifier",
  results: "Results",
};

interface Props {
  activeStage: string;
  onJump: (id: string) => void;
}

export default function PipelineNav({ activeStage, onJump }: Props) {
  const i = STAGE_ORDER.indexOf(activeStage as (typeof STAGE_ORDER)[number]);
  const prev = i > 0 ? STAGE_ORDER[i - 1] : null;
  const next = i >= 0 && i < STAGE_ORDER.length - 1 ? STAGE_ORDER[i + 1] : null;

  return (
    <div className="pipeline-nav">
      <button className="btn ghost" disabled={!prev} onClick={() => prev && onJump(prev)}>
        {prev ? `← ${LABEL[prev]}` : ""}
      </button>
      <div className="step mono">
        stage {Math.max(0, i) + 1} of {STAGE_ORDER.length}
      </div>
      <button className="btn primary" disabled={!next} onClick={() => next && onJump(next)}>
        {next ? `${LABEL[next]} →` : "—"}
      </button>
    </div>
  );
}

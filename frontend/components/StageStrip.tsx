"use client";

import { cx } from "@/lib/cx";

export interface StageDef {
  id: string;
  label: string;
  count?: number | null;
  note: string;
  warn?: number;
  err?: number;
  done?: boolean;
  pulse?: boolean;
}

interface Props {
  stages: StageDef[];
  active: string;
  onJump: (id: string) => void;
}

export default function StageStrip({ stages, active, onJump }: Props) {
  return (
    <div className="stages">
      {stages.map((s, i) => (
        <button
          key={s.id}
          className={cx(
            "stage",
            active === s.id && "active",
            s.done && "done",
            s.pulse && "pulse",
          )}
          onClick={() => onJump(s.id)}
        >
          <div className="stage-head">
            <div className="stage-dot" />
            <span className="stage-num">0{i + 1}</span>
            <span className="stage-label">{s.label}</span>
          </div>
          <div className="stage-meta">
            <span className="stage-count">
              {s.count != null ? `${s.count} events` : s.note}
            </span>
            {!!s.warn && s.warn > 0 && (
              <span className="stage-flag-chip warn">{s.warn} warn</span>
            )}
            {!!s.err && s.err > 0 && (
              <span className="stage-flag-chip err">{s.err} err</span>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

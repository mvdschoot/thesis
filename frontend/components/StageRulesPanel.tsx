"use client";

import { cx } from "@/lib/cx";
import type { RuleSummary } from "@/lib/rules";
import type { QualityFlag } from "@/lib/types";

interface Sample {
  category?: string;
  [k: string]: unknown;
}

interface Props {
  title: string;
  eyebrow: string;
  blurb: string;
  /** Read-only projection of the active config's stage section. */
  summary: RuleSummary[];
  /** Top-level YAML key the user would edit to change this stage. */
  sectionKey: "clean" | "validate" | "qualify";
  onEditYaml?: () => void;
  sample: Sample;
  sampleAfter: Sample;
  sampleFlags?: QualityFlag[];
}

export default function StageRulesPanel({
  title,
  eyebrow,
  blurb,
  summary,
  sectionKey,
  onEditYaml,
  sample,
  sampleAfter,
  sampleFlags,
}: Props) {
  const enabledCount = summary.filter((r) => r.enabled).length;

  return (
    <div>
      <div className="section-sub">{eyebrow}</div>
      <h2 className="section-title">{title}</h2>
      <p className="muted" style={{ maxWidth: 720, marginTop: 0 }}>
        {blurb}
      </p>

      <div className="two-pane" style={{ marginTop: 24 }}>
        <div className="card">
          <div className="card-head">
            <span className="eyebrow">
              Active rules · {enabledCount} of {summary.length} ·{" "}
              <span className="mono">{sectionKey}</span> block
            </span>
            {onEditYaml && (
              <button
                className="btn"
                onClick={onEditYaml}
                style={{ marginLeft: "auto" }}
                title={`Edit the ${sectionKey} block in the YAML editor`}
              >
                Edit in YAML →
              </button>
            )}
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {summary.map((r) => (
              <div
                key={r.name}
                style={{
                  padding: "14px 18px",
                  borderBottom: "1px solid var(--line-2)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  opacity: r.enabled ? 1 : 0.55,
                }}
              >
                <div className={cx("switch", r.enabled && "on")} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 500 }}>{r.label}</span>
                    <span className="chip mono">{r.name}</span>
                    {!r.enabled && (
                      <span className="chip" style={{ color: "var(--muted)" }}>
                        disabled
                      </span>
                    )}
                  </div>
                  {r.params && (
                    <pre
                      className="code-pre"
                      style={{ fontSize: 11, marginTop: 6, maxHeight: 110 }}
                    >
                      {JSON.stringify(r.params, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="eyebrow">Sample event · live preview</span>
            {sample.category && <span className="chip">{sample.category}</span>}
          </div>
          <div className="card-body">
            <div className="eyebrow" style={{ marginBottom: 6 }}>
              Before
            </div>
            <pre className="code-pre" style={{ maxHeight: 130 }}>
              {JSON.stringify(sample, null, 2)}
            </pre>
            <div className="ascii-sep">↓ rules apply ↓</div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>
              After
            </div>
            <pre className="code-pre" style={{ maxHeight: 130 }}>
              {JSON.stringify(sampleAfter, null, 2)}
            </pre>
            {sampleFlags && sampleFlags.length > 0 && (
              <>
                <div className="spacer-sm" />
                <div className="eyebrow" style={{ marginBottom: 6 }}>
                  Flags emitted
                </div>
                {sampleFlags.map((f, i) => (
                  <div key={i} className={cx("qflag", f.severity)}>
                    <div className="qf-bar" />
                    <div>
                      <div className="qf-code">{f.code}</div>
                      <div className="qf-msg">{f.message}</div>
                      <div className="qf-meta">
                        stage = {f.stage} · severity = {f.severity}
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

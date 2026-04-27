"use client";

import { cx } from "@/lib/cx";
import type { QualityFlag, RuleToggle } from "@/lib/types";

interface Sample {
  category?: string;
  [k: string]: unknown;
}

interface Props {
  title: string;
  eyebrow: string;
  blurb: string;
  rules: RuleToggle[];
  setRules: (next: RuleToggle[]) => void;
  sample: Sample;
  sampleAfter: Sample;
  sampleFlags?: QualityFlag[];
}

export default function StageRulesPanel({
  title,
  eyebrow,
  blurb,
  rules,
  setRules,
  sample,
  sampleAfter,
  sampleFlags,
}: Props) {
  const toggle = (id: string) =>
    setRules(rules.map((r) => (r.id === id ? { ...r, on: !r.on } : r)));

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
              Active rules · {rules.filter((r) => r.on).length} of {rules.length}
            </span>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {rules.map((r) => (
              <div
                key={r.id}
                style={{
                  padding: "14px 18px",
                  borderBottom: "1px solid var(--line-2)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                }}
              >
                <div
                  className={cx("switch", r.on && "on")}
                  onClick={() => toggle(r.id)}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 500 }}>{r.name}</span>
                    <span className="chip mono">{r.id}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {r.desc}
                  </div>
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

"use client";

import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import {
  suggestConfigFix,
  type AdapterDiagnostics,
  type RuleDiagnostic,
  type SkippedReason,
} from "@/lib/api";

interface Props {
  diagnostics: AdapterDiagnostics | null | undefined;
  yamlText: string;
  sampleRecord: unknown;
  onApplyYaml: (yaml: string) => void | Promise<void>;
}

const SKIP_CODE_LABELS: Record<string, string> = {
  predicate_mismatch: "match clause rejected record",
  no_adapter_registered: "no adapter registered",
  iterate_path_none: "iterate path missing",
  iterate_not_list: "iterate target not an array",
  iterate_empty: "iterate target is empty",
  iterate_object_source_none: "iterate_object source missing",
  iterate_object_source_not_dict: "iterate_object source not an object",
  iterate_object_keys_missing: "no entry keys present",
  parent_rule_empty: "parent rule produced no events",
};

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "string") return JSON.stringify(v);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return JSON.stringify(v);
  return JSON.stringify(v);
}

function ReasonRow({ r }: { r: SkippedReason }) {
  const label = SKIP_CODE_LABELS[r.code] ?? r.code;
  return (
    <div
      style={{
        padding: "8px 10px",
        borderTop: "1px solid var(--line)",
        fontSize: 13,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span className="chip warn">{label}</span>
        {r.path && <span className="mono muted">path: {r.path}</span>}
        <span className="muted" style={{ fontSize: 12 }}>
          record #{r.record_index}
        </span>
      </div>
      <div style={{ marginTop: 4 }}>{r.detail}</div>
      {(r.expected !== undefined && r.expected !== null) || (r.actual !== undefined && r.actual !== null) ? (
        <div className="mono muted" style={{ marginTop: 4, fontSize: 12 }}>
          expected {fmtVal(r.expected)} · got {fmtVal(r.actual)}
        </div>
      ) : null}
      {r.record_keys && r.record_keys.length > 0 && (
        <div className="mono muted" style={{ marginTop: 4, fontSize: 12 }}>
          record keys: {r.record_keys.join(", ")}
        </div>
      )}
    </div>
  );
}

function RuleCard({ rd }: { rd: RuleDiagnostic }) {
  const ok = rd.events_emitted > 0;
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="card-head">
        <span className="eyebrow">Rule</span>
        <span className="mono" style={{ marginLeft: 8 }}>{rd.rule_id}</span>
        <span className={cx("chip", ok ? "ok" : "err")} style={{ marginLeft: "auto" }}>
          {rd.events_emitted} events
        </span>
        <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
          {rd.records_seen} record{rd.records_seen === 1 ? "" : "s"} seen
        </span>
      </div>
      {rd.skipped_reasons.length === 0 ? (
        <div style={{ padding: "10px 14px", fontSize: 13 }} className="muted">
          {ok
            ? "Rule emitted events on every record."
            : "Rule produced no events; no skip reasons captured."}
        </div>
      ) : (
        rd.skipped_reasons.map((r, i) => <ReasonRow key={i} r={r} />)
      )}
    </div>
  );
}

export default function DebugPanel({
  diagnostics,
  yamlText,
  sampleRecord,
  onApplyYaml,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggested, setSuggested] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  // Send the first record that triggered any skip — most actionable for the LLM.
  // Falls back to the whole input when we can't slice it (CSV string, non-array JSON).
  const failingRecord = useMemo(() => {
    if (!diagnostics || !Array.isArray(sampleRecord) || sampleRecord.length === 0) {
      return sampleRecord;
    }
    const firstPred = diagnostics.predicate_failures[0]?.record_index;
    const firstSkip = diagnostics.rules
      .flatMap((r) => r.skipped_reasons.map((s) => s.record_index))
      .find((i) => i >= 0);
    const idx = firstPred ?? firstSkip ?? 0;
    return sampleRecord[idx] ?? sampleRecord[0];
  }, [diagnostics, sampleRecord]);

  async function handleSuggestFix() {
    if (!diagnostics) return;
    setBusy(true);
    setError(null);
    setSuggested(null);
    setApplied(false);
    try {
      const res = await suggestConfigFix({
        yaml: yamlText,
        diagnostics,
        sample_record: failingRecord,
      });
      setSuggested(res.yaml);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!suggested) return;
    setApplying(true);
    try {
      await onApplyYaml(suggested);
      setApplied(true);
    } catch {
      // The parent surfaces the failure message; keep the card open for retry.
    } finally {
      setApplying(false);
    }
  }

  if (!diagnostics) {
    return (
      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ padding: "14px 16px" }} className="muted">
          No diagnostics available. Run the pipeline to populate per-rule debug info.
        </div>
      </div>
    );
  }

  const anyRuleEmpty = diagnostics.rules.some((r) => r.events_emitted === 0);
  const headlineBad = diagnostics.records_unmatched > 0 || anyRuleEmpty || diagnostics.events_emitted === 0;

  return (
    <div style={{ marginTop: 14 }}>
      <div
        className="card"
        style={{
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 240 }}>
          <div className="eyebrow">Adapter diagnostics</div>
          <div style={{ marginTop: 4 }}>
            <span className={cx("chip", diagnostics.records_unmatched === 0 ? "ok" : "err")}>
              {diagnostics.records_matched} / {diagnostics.records_total} records matched
            </span>{" "}
            <span className={cx("chip", diagnostics.events_emitted > 0 ? "ok" : "err")}>
              {diagnostics.events_emitted} events emitted
            </span>{" "}
            <span className="chip">{diagnostics.rules.length} rules</span>
          </div>
        </div>
        <button
          className={cx("btn", headlineBad && "primary")}
          onClick={handleSuggestFix}
          disabled={busy || (!headlineBad)}
          title={
            headlineBad
              ? "Send the config + diagnostics + a sample record to the LLM and request a patched YAML."
              : "Everything emitted events — no fix needed."
          }
        >
          {busy ? "Asking LLM…" : "Suggest fix with LLM"}
        </button>
      </div>

      {error && (
        <div className="qflag err" style={{ marginTop: 12 }}>
          <div className="qf-bar" />
          <div>
            <div className="qf-code">FIX_REQUEST_FAILED</div>
            <div className="qf-msg">{error}</div>
          </div>
        </div>
      )}

      {suggested && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-head">
            <span className="eyebrow">Suggested YAML</span>
            {applied && (
              <span className="chip ok" style={{ marginLeft: 8 }}>
                applied &amp; saved to backend
              </span>
            )}
            <button
              className="btn primary"
              style={{ marginLeft: "auto" }}
              onClick={handleApply}
              disabled={applying}
              title="Apply the patched YAML to the editor and save it to the backend config store."
            >
              {applying ? "Saving…" : applied ? "Apply & save again" : "Apply & save"}
            </button>
            <button
              className="btn"
              style={{ marginLeft: 8 }}
              onClick={() => {
                setSuggested(null);
                setApplied(false);
              }}
            >
              Discard
            </button>
          </div>
          <pre
            className="mono"
            style={{
              margin: 0,
              padding: 14,
              maxHeight: 360,
              overflow: "auto",
              fontSize: 12,
              whiteSpace: "pre",
            }}
          >
            {suggested}
          </pre>
        </div>
      )}

      {diagnostics.predicate_failures.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-head">
            <span className="eyebrow">Match predicate</span>
            <span className="chip err" style={{ marginLeft: "auto" }}>
              {diagnostics.records_unmatched} unmatched
            </span>
          </div>
          <div style={{ padding: "8px 14px", fontSize: 13 }} className="muted">
            These records were excluded by the <span className="mono">match.record</span>{" "}
            block before any emit rule ran. The first failing clause is shown below.
          </div>
          {diagnostics.predicate_failures.map((r, i) => (
            <ReasonRow key={i} r={r} />
          ))}
        </div>
      )}

      {diagnostics.rules.map((rd) => (
        <RuleCard key={rd.rule_id} rd={rd} />
      ))}

      {diagnostics.rules.length === 0 && diagnostics.predicate_failures.length === 0 && (
        <div
          className="card muted"
          style={{ marginTop: 12, padding: "14px 16px" }}
        >
          No rules executed and no predicate failures recorded — likely an empty input.
        </div>
      )}
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import { exportBundle, FHIR_BASE, type ExportSummary } from "@/lib/fhirServer";
import type { FhirBundle } from "@/lib/types";

interface Props {
  bundle: FhirBundle | null;
  /** Open the top-level FHIR Server dashboard (set after a successful export). */
  onOpenServer?: () => void;
}

type ExportState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; summary: ExportSummary }
  | { status: "error"; message: string };

function counts(bundle: FhirBundle): { kind: string; n: number }[] {
  const tally = new Map<string, number>();
  for (const e of bundle.entry ?? []) {
    const kind = e.resource?.resourceType ?? "Unknown";
    tally.set(kind, (tally.get(kind) ?? 0) + 1);
  }
  return Array.from(tally.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([kind, n]) => ({ kind, n }));
}

interface CodingTally {
  total: number;
  coded: number;
}

function tallyCoding(bundle: FhirBundle): CodingTally {
  // Walk every Observation / QR resource and count code.coding[] vs text-only.
  let total = 0;
  let coded = 0;
  for (const e of bundle.entry ?? []) {
    const r = e.resource as Record<string, unknown> | undefined;
    if (!r) continue;
    const kind = r.resourceType;
    if (kind !== "Observation" && kind !== "QuestionnaireResponse") continue;
    if (kind === "Observation") {
      total += 1;
      const code = r.code as { coding?: unknown[] } | undefined;
      if (Array.isArray(code?.coding) && code.coding.length > 0) coded += 1;
    }
  }
  return { total, coded };
}

// At very large bundle sizes, pretty-printing the entire bundle blocks the
// main thread for seconds and produces multi-MB strings the DOM has to lay
// out as one text node. We pretty-print at most this many entries for the
// on-screen preview; Copy / Download still operate on the full bundle.
const PREVIEW_MAX_ENTRIES = 100;

export default function FhirBundlePanel({ bundle, onOpenServer }: Props) {
  const [copied, setCopied] = useState(false);
  const [exp, setExp] = useState<ExportState>({ status: "idle" });

  const entryCount = bundle?.entry?.length ?? 0;
  const previewTruncated = entryCount > PREVIEW_MAX_ENTRIES;

  // Preview: pretty-print at most PREVIEW_MAX_ENTRIES entries. The full
  // bundle is only stringified inside copy() / download() handlers.
  const previewJson = useMemo(() => {
    if (!bundle) return "";
    if (!previewTruncated) return JSON.stringify(bundle, null, 2);
    const sliced = {
      ...bundle,
      entry: (bundle.entry ?? []).slice(0, PREVIEW_MAX_ENTRIES),
    };
    return JSON.stringify(sliced, null, 2);
  }, [bundle, previewTruncated]);

  const chips = useMemo(() => (bundle ? counts(bundle) : []), [bundle]);
  const codingTally = useMemo(
    () => (bundle ? tallyCoding(bundle) : { total: 0, coded: 0 }),
    [bundle],
  );

  if (!bundle) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-body">
          <p className="muted">
            FHIR output disabled — set <span className="mono">fhir.enabled: true</span> in the
            active pipeline config (or include a <span className="mono">fhir:</span> block at all)
            to populate this view.
          </p>
        </div>
      </div>
    );
  }

  function copy() {
    if (!bundle) return;
    const full = JSON.stringify(bundle, null, 2);
    void navigator.clipboard?.writeText(full).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      },
      () => setCopied(false),
    );
  }

  function download() {
    if (!bundle) return;
    const full = JSON.stringify(bundle, null, 2);
    const blob = new Blob([full], { type: "application/fhir+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "bundle.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function exportToServer() {
    if (!bundle) return;
    setExp({ status: "running" });
    try {
      const summary = await exportBundle(bundle);
      setExp({ status: "done", summary });
    } catch (e) {
      setExp({ status: "error", message: (e as Error).message });
    }
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <span className="eyebrow">
          FHIR R4 · <span className="mono">{bundle.type}</span> bundle ·{" "}
          {bundle.entry?.length ?? 0} entries
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn" onClick={copy} title="Copy bundle JSON to clipboard">
            {copied ? "Copied ✓" : "Copy JSON"}
          </button>
          <button className="btn" onClick={download} title="Download bundle.json">
            Download
          </button>
          <button
            className="btn primary"
            onClick={exportToServer}
            disabled={exp.status === "running"}
            title={`Upsert this bundle into the HAPI FHIR server at ${FHIR_BASE}`}
          >
            {exp.status === "running" ? (
              <>
                <span className="spin" /> Exporting…
              </>
            ) : (
              <>Export to FHIR server</>
            )}
          </button>
        </div>
      </div>
      <div className="card-body">
        {exp.status === "done" && (
          <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className={cx("chip mono", exp.summary.errors.length === 0 ? "ok" : "warn")}>
              {exp.summary.ok}/{exp.summary.total} resources upserted
              {exp.summary.errors.length > 0 ? ` · ${exp.summary.errors.length} failed` : " ✓"}
            </span>
            {onOpenServer && (
              <button
                type="button"
                onClick={onOpenServer}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--accent, #1f6feb)",
                  cursor: "pointer",
                  padding: 0,
                  textDecoration: "underline",
                  font: "inherit",
                }}
              >
                Open FHIR Server →
              </button>
            )}
          </div>
        )}
        {exp.status === "error" && (
          <div className="qflag err" style={{ marginBottom: 12 }}>
            <div className="qf-bar" />
            <div>
              <div className="qf-code">FHIR_EXPORT_FAILED</div>
              <div className="qf-msg">{exp.message}</div>
            </div>
          </div>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {chips.map(({ kind, n }) => (
            <span key={kind} className="chip mono">
              {n} {kind}
            </span>
          ))}
        </div>
        <pre
          className="code-pre"
          style={{ maxHeight: 520, fontSize: 12, overflow: "auto" }}
        >
          {previewJson}
        </pre>
        {previewTruncated && (
          <p className="help" style={{ marginTop: 8 }}>
            Showing first {PREVIEW_MAX_ENTRIES.toLocaleString()} of{" "}
            {entryCount.toLocaleString()} entries · use Download for the full bundle.
          </p>
        )}
        <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
          {codingTally.total > 0 && (
            <>
              <span
                className={cx(
                  "chip mono",
                  codingTally.coded === codingTally.total
                    ? "ok"
                    : codingTally.coded === 0
                    ? "warn"
                    : "info",
                )}
                style={{ marginRight: 8 }}
              >
                Observation.code · {codingTally.coded}/{codingTally.total} with coding[]
              </span>
            </>
          )}
          <span className="mono">CodeableConcept.text</span> is always present as the human-readable
          fallback. Use the <span className="mono">Concepts</span> tab to bind LOINC / UCUM /
          SNOMED CT codings via OMOPHub, then re-transform to populate{" "}
          <span className="mono">coding[]</span>.
        </p>
      </div>
    </div>
  );
}

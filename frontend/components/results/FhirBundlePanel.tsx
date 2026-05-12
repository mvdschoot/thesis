"use client";

import { useMemo, useState } from "react";

import type { FhirBundle } from "@/lib/types";

interface Props {
  bundle: FhirBundle | null;
}

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

export default function FhirBundlePanel({ bundle }: Props) {
  const [copied, setCopied] = useState(false);

  const json = useMemo(
    () => (bundle ? JSON.stringify(bundle, null, 2) : ""),
    [bundle],
  );
  const chips = useMemo(() => (bundle ? counts(bundle) : []), [bundle]);

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
    void navigator.clipboard?.writeText(json).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      },
      () => setCopied(false),
    );
  }

  function download() {
    const blob = new Blob([json], { type: "application/fhir+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "bundle.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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
        </div>
      </div>
      <div className="card-body">
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
          {json}
        </pre>
        <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
          Text-only <span className="mono">CodeableConcept</span> fields by design — codings
          (LOINC / SNOMED / UCUM) are populated by the future <span className="mono">MAPPED</span>{" "}
          stage. The bundle is structurally FHIR R4-conformant and posts cleanly to a transaction
          endpoint, but downstream code-based queries will require the codings.
        </p>
      </div>
    </div>
  );
}

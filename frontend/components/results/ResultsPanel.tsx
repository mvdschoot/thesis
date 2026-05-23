"use client";

import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import type { AdapterDiagnostics } from "@/lib/api";
import type { CanonicalEvent, Coding, ConceptSlot, FhirBundle } from "@/lib/types";

import ConceptsPanel from "./ConceptsPanel";
import DebugPanel from "./DebugPanel";
import EventDrawer from "./EventDrawer";
import EventStats from "./EventStats";
import EventTable from "./EventTable";
import FhirBundlePanel from "./FhirBundlePanel";

interface Props {
  events: CanonicalEvent[];
  source: "live" | "simulated";
  bundle: FhirBundle | null;
  conceptSlots: ConceptSlot[];
  conceptMappings: Record<string, Coding>;
  onConceptChange: (key: string, coding: Coding | null) => void;
  onRerunWithConcepts: () => void;
  rerunning: boolean;
  adapterDiagnostics?: AdapterDiagnostics | null;
  yamlText: string;
  inputData: unknown;
  onApplyYaml: (yaml: string) => void;
}

type View = "events" | "concepts" | "fhir" | "debug";

export default function ResultsPanel({
  events,
  source,
  bundle,
  conceptSlots,
  conceptMappings,
  onConceptChange,
  onRerunWithConcepts,
  rerunning,
  adapterDiagnostics,
  yamlText,
  inputData,
  onApplyYaml,
}: Props) {
  const [view, setView] = useState<View>("events");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = events.find((e) => e.event_id === selectedId) ?? null;

  const unboundCount = useMemo(
    () =>
      conceptSlots.filter(
        (s) =>
          (s.kind === "code" || s.kind === "unit" || s.kind === "component") &&
          !conceptMappings[s.key],
      ).length,
    [conceptSlots, conceptMappings],
  );

  const debugAlert = useMemo(() => {
    if (!adapterDiagnostics) return false;
    if (adapterDiagnostics.records_unmatched > 0) return true;
    if (adapterDiagnostics.events_emitted === 0) return true;
    return adapterDiagnostics.rules.some((r) => r.events_emitted === 0);
  }, [adapterDiagnostics]);

  return (
    <div>
      <div className="section-sub">Output · CanonicalEvent[] + FHIR Bundle</div>
      <h2 className="section-title">Results</h2>
      <p className="muted" style={{ maxWidth: 720, marginTop: 0 }}>
        Stateless per-request output. Failed-validation events are tagged, not dropped — consumers choose their own filter point.
        {source === "simulated" && (
          <>
            {" "}
            <span className="chip warn" style={{ marginLeft: 6 }}>
              simulated
            </span>{" "}
            Run the pipeline (top-right) to replace these with live backend output.
          </>
        )}
      </p>

      <div style={{ display: "flex", gap: 8, margin: "12px 0 6px" }}>
        <button
          className={cx("btn", view === "events" && "primary")}
          onClick={() => setView("events")}
        >
          Events ({events.length})
        </button>
        <button
          className={cx("btn", view === "concepts" && "primary")}
          onClick={() => setView("concepts")}
          title="Bind LOINC / UCUM / FHIR codings to the detected concept slots"
        >
          Concepts{" "}
          {conceptSlots.length > 0 &&
            (unboundCount > 0
              ? `(${unboundCount}/${conceptSlots.length} unbound)`
              : `(${conceptSlots.length} ✓)`)}
        </button>
        <button
          className={cx("btn", view === "fhir" && "primary")}
          onClick={() => setView("fhir")}
          title="View the FHIR R4 Bundle produced by the pipeline"
        >
          FHIR Bundle{bundle ? ` (${bundle.entry?.length ?? 0})` : ""}
        </button>
        <button
          className={cx("btn", view === "debug" && "primary")}
          onClick={() => setView("debug")}
          title="Why did the adapter emit (or not emit) events? Per-rule diagnostics + LLM-suggested fix."
        >
          Debug
          {debugAlert && (
            <span
              aria-label="issues detected"
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "oklch(0.55 0.21 25)",
                marginLeft: 6,
                verticalAlign: "middle",
              }}
            />
          )}
        </button>
      </div>

      {view === "events" && (
        <>
          <EventStats events={events} />
          {events.length === 0 && adapterDiagnostics && (
            <div className="card" style={{ marginTop: 16, padding: "12px 16px" }}>
              <div style={{ fontSize: 13 }}>
                <strong>0 events emitted.</strong>{" "}
                <button
                  type="button"
                  onClick={() => setView("debug")}
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
                  Open the Debug tab
                </button>{" "}
                to see which match clause or emit rule failed.
              </div>
            </div>
          )}
          <EventTable events={events} selectedId={selectedId} onSelect={setSelectedId} />
          <EventDrawer event={selected} onClose={() => setSelectedId(null)} />
        </>
      )}

      {view === "concepts" && (
        <ConceptsPanel
          slots={conceptSlots}
          mappings={conceptMappings}
          onChange={onConceptChange}
          onRerun={onRerunWithConcepts}
          running={rerunning}
        />
      )}

      {view === "fhir" && <FhirBundlePanel bundle={bundle} />}

      {view === "debug" && (
        <DebugPanel
          diagnostics={adapterDiagnostics}
          yamlText={yamlText}
          sampleRecord={inputData}
          onApplyYaml={onApplyYaml}
        />
      )}
    </div>
  );
}

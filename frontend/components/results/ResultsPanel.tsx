"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cx } from "@/lib/cx";
import type { AdapterDiagnostics, NoMatchSlot } from "@/lib/api";
import type { CanonicalEvent, Coding, ConceptSlot, FhirBundle, OmopCdmOutput } from "@/lib/types";

import ConceptsPanel from "./ConceptsPanel";
import DebugPanel from "./DebugPanel";
import EventDrawer from "./EventDrawer";
import EventStats from "./EventStats";
import EventTable from "./EventTable";
import FhirBundlePanel from "./FhirBundlePanel";
import OmopCdmPanel from "./OmopCdmPanel";

interface Props {
  events: CanonicalEvent[];
  source: "live" | "simulated";
  bundle: FhirBundle | null;
  omopCdm: OmopCdmOutput | null;
  conceptSlots: ConceptSlot[];
  conceptMappings: Record<string, Coding>;
  onConceptChange: (key: string, coding: Coding | null) => void;
  onBulkConceptChange: (mappings: Record<string, Coding>) => void;
  conceptNoMatches: Record<string, NoMatchSlot>;
  onNoMatchesChange: (noMatches: Record<string, NoMatchSlot>) => void;
  onRerunWithConcepts: () => void;
  rerunning: boolean;
  adapterDiagnostics?: AdapterDiagnostics | null;
  yamlText: string;
  inputData: unknown;
  onApplyYaml: (yaml: string) => void | Promise<void>;
  scanPhase?: boolean;
  onOpenServer?: () => void;
}

type View = "events" | "concepts" | "fhir" | "omop" | "debug";

export default function ResultsPanel({
  events,
  source,
  bundle,
  omopCdm,
  conceptSlots,
  conceptMappings,
  onConceptChange,
  onBulkConceptChange,
  conceptNoMatches,
  onNoMatchesChange,
  onRerunWithConcepts,
  rerunning,
  adapterDiagnostics,
  yamlText,
  inputData,
  onApplyYaml,
  scanPhase,
  onOpenServer,
}: Props) {
  const [view, setView] = useState<View>("events");
  const prevScanPhase = useRef(scanPhase);
  useEffect(() => {
    if (scanPhase && !prevScanPhase.current) {
      setView("concepts");
    }
    prevScanPhase.current = scanPhase;
  }, [scanPhase]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = events.find((e) => e.event_id === selectedId) ?? null;

  const [showJson, setShowJson] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);

  const eventsJson = useMemo(
    () => JSON.stringify(events.slice(0, 5), null, 2),
    [events],
  );

  function copyJson() {
    void navigator.clipboard?.writeText(eventsJson).then(
      () => {
        setCopiedJson(true);
        setTimeout(() => setCopiedJson(false), 1400);
      },
      () => setCopiedJson(false),
    );
  }

  const unboundCount = useMemo(
    () =>
      conceptSlots.filter(
        (s) =>
          (s.kind === "code" || s.kind === "unit") &&
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

  const omopRowCount = omopCdm
    ? (omopCdm.stats?.measurement_count ?? 0) + (omopCdm.stats?.observation_count ?? 0)
    : 0;

  return (
    <div>
      <div className="section-sub">Output · CanonicalEvent[] + FHIR Bundle + OMOP CDM</div>
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

      {scanPhase && (
        <div className="card" style={{ marginBottom: 14, padding: "10px 16px", borderLeft: "3px solid var(--accent, #5af)" }}>
          <strong>Concept scan complete</strong> — {conceptSlots.length} slot{conceptSlots.length !== 1 ? "s" : ""} found from a 100-record sample.
          Map your concepts below, then click <em>Transform all</em> to process the full dataset.
        </div>
      )}

      <div style={{ display: "flex", gap: 8, margin: "12px 0 6px", flexWrap: "wrap" }}>
        <button
          className={cx("btn", view === "events" && "primary")}
          onClick={() => setView("events")}
          disabled={scanPhase}
          style={scanPhase ? { opacity: 0.5 } : undefined}
        >
          Events {scanPhase ? "" : `(${events.length})`}
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
          disabled={scanPhase}
          style={scanPhase ? { opacity: 0.5 } : undefined}
          title="View the FHIR R4 Bundle produced by the pipeline"
        >
          FHIR Bundle{!scanPhase && bundle ? ` (${bundle.entry?.length ?? 0})` : ""}
        </button>
        <button
          className={cx("btn", view === "omop" && "primary")}
          onClick={() => setView("omop")}
          disabled={scanPhase}
          style={scanPhase ? { opacity: 0.5 } : undefined}
          title="View the OMOP CDM v5.4 tables produced by the pipeline"
        >
          OMOP CDM{!scanPhase && omopRowCount > 0 ? ` (${omopRowCount})` : ""}
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
          <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0" }}>
            <button
              className={cx("btn", showJson && "primary")}
              onClick={() => setShowJson((v) => !v)}
              disabled={events.length === 0}
              title="Show the raw canonical-event JSON (first 5)"
            >
              {showJson ? "Hide JSON" : "Show JSON"}
            </button>
            {showJson && events.length > 0 && (
              <button className="btn ghost" onClick={copyJson}>
                {copiedJson ? "Copied ✓" : "Copy"}
              </button>
            )}
            {events.length > 5 && (
              <span className="muted" style={{ fontSize: 12 }}>
                showing first 5 of {events.length}
              </span>
            )}
          </div>
          {showJson && events.length > 0 && (
            <pre className="code-pre" style={{ marginBottom: 14 }}>
              {eventsJson}
            </pre>
          )}
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
          noMatches={conceptNoMatches}
          onChange={onConceptChange}
          onBulkChange={onBulkConceptChange}
          onNoMatchesChange={onNoMatchesChange}
          onRerun={onRerunWithConcepts}
          running={rerunning}
        />
      )}

      {view === "fhir" && <FhirBundlePanel bundle={bundle} onOpenServer={onOpenServer} />}

      {view === "omop" && <OmopCdmPanel cdm={omopCdm} />}

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

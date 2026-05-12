"use client";

import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import type { CanonicalEvent, Coding, ConceptSlot, FhirBundle } from "@/lib/types";

import ConceptsPanel from "./ConceptsPanel";
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
}

type View = "events" | "concepts" | "fhir";

export default function ResultsPanel({
  events,
  source,
  bundle,
  conceptSlots,
  conceptMappings,
  onConceptChange,
  onRerunWithConcepts,
  rerunning,
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
      </div>

      {view === "events" && (
        <>
          <EventStats events={events} />
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
    </div>
  );
}

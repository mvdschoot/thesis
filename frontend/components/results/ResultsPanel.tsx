"use client";

import { useState } from "react";

import type { CanonicalEvent } from "@/lib/types";

import EventDrawer from "./EventDrawer";
import EventStats from "./EventStats";
import EventTable from "./EventTable";

interface Props {
  events: CanonicalEvent[];
  source: "live" | "simulated";
}

export default function ResultsPanel({ events, source }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = events.find((e) => e.event_id === selectedId) ?? null;

  return (
    <div>
      <div className="section-sub">Output · CanonicalEvent[]</div>
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

      <EventStats events={events} />
      <EventTable events={events} selectedId={selectedId} onSelect={setSelectedId} />
      <EventDrawer event={selected} onClose={() => setSelectedId(null)} />
    </div>
  );
}

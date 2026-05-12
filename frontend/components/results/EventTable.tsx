"use client";

import { useEffect, useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import type { CanonicalEvent } from "@/lib/types";

type Filter = "all" | "warn" | "err" | "ok";

const PAGE_SIZE = 200;

interface Props {
  events: CanonicalEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function chipClassFor(severity: string): string {
  if (severity === "error") return "chip err";
  if (severity === "warning") return "chip warn";
  return "chip info";
}

function plausibilityChip(p: string | null): string {
  if (p === "ok") return "chip ok";
  if (p === "review") return "chip warn";
  if (p === "exclude") return "chip err";
  return "chip";
}

export default function EventTable({ events, selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter((e) => {
      if (filter === "warn") return e.quality.flags.some((f) => f.severity === "warning");
      if (filter === "err") return e.quality.flags.some((f) => f.severity === "error");
      if (filter === "ok") return e.quality.flags.length === 0;
      return true;
    });
  }, [events, filter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  useEffect(() => {
    setPage(0);
  }, [filter, events]);

  return (
    <div className="card">
      <div className="card-head">
        <span className="eyebrow">Events</span>
        <div className="seg" style={{ marginLeft: "auto" }}>
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>
            all
          </button>
          <button className={filter === "ok" ? "on" : ""} onClick={() => setFilter("ok")}>
            ok
          </button>
          <button className={filter === "warn" ? "on" : ""} onClick={() => setFilter("warn")}>
            warn
          </button>
          <button className={filter === "err" ? "on" : ""} onClick={() => setFilter("err")}>
            err
          </button>
        </div>
      </div>
      <div style={{ maxHeight: 460, overflow: "auto" }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>timestamp</th>
              <th>category</th>
              <th>type</th>
              <th>value</th>
              <th>unit</th>
              <th>flags</th>
              <th>plausibility</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((e) => {
              const [date, rest] = e.timestamp.split("T");
              const time = rest?.replace("Z", "");
              return (
                <tr
                  key={e.event_id}
                  className={cx(selectedId === e.event_id && "selected")}
                  onClick={() => onSelect(e.event_id)}
                >
                  <td className="mono">
                    <span className="ts">{date}</span> {time}
                  </td>
                  <td className="mono">{e.category}</td>
                  <td>
                    <span className="chip">{e.type}</span>
                  </td>
                  <td className="mono">
                    {typeof e.payload.value === "object"
                      ? "{...}"
                      : String(e.payload.value)}
                  </td>
                  <td className="mono muted">{e.payload.unit ?? "—"}</td>
                  <td>
                    {e.quality.flags.length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      e.quality.flags.map((f, i) => (
                        <span
                          key={i}
                          className={chipClassFor(f.severity)}
                          style={{ marginRight: 4 }}
                        >
                          {f.code}
                        </span>
                      ))
                    )}
                  </td>
                  <td>
                    <span className={plausibilityChip(e.quality.plausibility)}>
                      {e.quality.plausibility ?? "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {filtered.length > PAGE_SIZE && (
        <div
          className="card-head"
          style={{
            padding: "8px 14px",
            borderTop: "1px solid var(--line)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span className="muted" style={{ fontSize: 12 }}>
            Page {safePage + 1} of {pageCount} · {filtered.length.toLocaleString()} events
          </span>
          <div className="seg" style={{ marginLeft: "auto" }}>
            <button
              disabled={safePage === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              prev
            </button>
            <button
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            >
              next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

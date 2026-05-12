"use client";

import { useMemo } from "react";

import type { CanonicalEvent } from "@/lib/types";

interface Props {
  events: CanonicalEvent[];
}

export default function EventStats({ events }: Props) {
  const stats = useMemo(() => {
    let flags = 0;
    let warnings = 0;
    let errors = 0;
    let ok = 0;
    let review = 0;
    let exclude = 0;
    let daily = 0;
    let interval = 0;
    for (const e of events) {
      for (const f of e.quality.flags) {
        flags++;
        if (f.severity === "warning") warnings++;
        else if (f.severity === "error") errors++;
      }
      const p = e.quality.plausibility;
      if (p === "ok") ok++;
      else if (p === "review") review++;
      else if (p === "exclude") exclude++;
      const g = e.granularity;
      if (g === "daily") daily++;
      else if (g === "interval") interval++;
    }
    return {
      total: events.length,
      ok,
      review,
      exclude,
      daily,
      interval,
      flags,
      warnings,
      errors,
    };
  }, [events]);

  return (
    <div className="stats" style={{ marginTop: 20 }}>
      <div className="stat">
        <div className="label">Events</div>
        <div className="value">{stats.total}</div>
        <div className="delta">
          {stats.daily} daily · {stats.interval} interval
        </div>
      </div>
      <div className="stat">
        <div className="label">Plausible · ok</div>
        <div className="value" style={{ color: "oklch(0.4 0.13 150)" }}>
          {stats.ok}
        </div>
        <div className="delta">no flags raised</div>
      </div>
      <div className="stat">
        <div className="label">Review</div>
        <div className="value" style={{ color: "oklch(0.45 0.13 65)" }}>
          {stats.review}
        </div>
        <div className="delta">≥1 warning</div>
      </div>
      <div className="stat">
        <div className="label">Quality flags</div>
        <div className="value">{stats.flags}</div>
        <div className="delta">
          {stats.warnings} warn · {stats.errors} err
        </div>
      </div>
    </div>
  );
}

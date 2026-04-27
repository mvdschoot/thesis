"use client";

import { useMemo } from "react";

import type { CanonicalEvent } from "@/lib/types";

interface Props {
  events: CanonicalEvent[];
}

export default function EventStats({ events }: Props) {
  const stats = useMemo(() => {
    const flagsTotal = events.reduce((s, e) => s + e.quality.flags.length, 0);
    const warnings = events.reduce(
      (s, e) => s + e.quality.flags.filter((f) => f.severity === "warning").length,
      0,
    );
    const errors = events.reduce(
      (s, e) => s + e.quality.flags.filter((f) => f.severity === "error").length,
      0,
    );
    return {
      total: events.length,
      ok: events.filter((e) => e.quality.plausibility === "ok").length,
      review: events.filter((e) => e.quality.plausibility === "review").length,
      exclude: events.filter((e) => e.quality.plausibility === "exclude").length,
      daily: events.filter((e) => e.granularity === "daily").length,
      interval: events.filter((e) => e.granularity === "interval").length,
      flags: flagsTotal,
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

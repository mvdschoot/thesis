"use client";

import { cx } from "@/lib/cx";
import type { CanonicalEvent } from "@/lib/types";

interface Props {
  event: CanonicalEvent | null;
  onClose: () => void;
}

export default function EventDrawer({ event, onClose }: Props) {
  return (
    <>
      <div className={cx("scrim", event && "open")} onClick={onClose} />
      <div className={cx("drawer", event && "open")}>
        {event && (
          <>
            <div className="drawer-head">
              <div style={{ flex: 1 }}>
                <div className="eyebrow">Canonical event</div>
                <div className="mono" style={{ fontSize: 12, color: "var(--ink)" }}>
                  {event.event_id}
                </div>
              </div>
              <button className="btn ghost" onClick={onClose}>
                Close ✕
              </button>
            </div>
            <div className="drawer-body">
              <div className="row">
                <div className="field">
                  <label>category</label>
                  <div>
                    <span className="chip accent">{event.category}</span>
                  </div>
                </div>
                <div className="field">
                  <label>stage</label>
                  <div>
                    <span className="chip solid">{event.stage}</span>
                  </div>
                </div>
                <div className="field">
                  <label>granularity</label>
                  <div>
                    <span className="chip">{event.granularity}</span>
                  </div>
                </div>
              </div>
              <div className="spacer-md" />

              <div className="eyebrow" style={{ marginBottom: 8 }}>
                Payload
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "110px 1fr",
                  rowGap: 6,
                  fontSize: 12,
                }}
              >
                <span className="muted mono">value</span>
                <span className="mono">
                  {typeof event.payload.value === "object"
                    ? JSON.stringify(event.payload.value)
                    : String(event.payload.value)}
                </span>
                <span className="muted mono">unit</span>
                <span className="mono">{event.payload.unit ?? "null"}</span>
                <span className="muted mono">label</span>
                <span>{event.payload.label}</span>
              </div>

              {event.payload.components && event.payload.components.length > 0 && (
                <>
                  <div className="spacer-md" />
                  <div className="eyebrow" style={{ marginBottom: 8 }}>
                    Components
                  </div>
                  <table className="tbl" style={{ fontSize: 11.5 }}>
                    <thead>
                      <tr>
                        <th>name</th>
                        <th>value</th>
                        <th>unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {event.payload.components.map((c, i) => (
                        <tr key={i} style={{ cursor: "default" }}>
                          <td className="mono">{c.name}</td>
                          <td className="mono">{String(c.value)}</td>
                          <td className="mono muted">{c.unit ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              <div className="spacer-md" />
              <div className="eyebrow" style={{ marginBottom: 8 }}>
                Quality
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "140px 1fr",
                  rowGap: 6,
                  fontSize: 12,
                  marginBottom: 10,
                }}
              >
                <span className="muted mono">conformance</span>
                <span className="mono">{event.quality.conformance}</span>
                <span className="muted mono">completeness</span>
                <span className="mono">{event.quality.completeness}</span>
                <span className="muted mono">plausibility</span>
                <span className="mono">{event.quality.plausibility}</span>
                <span className="muted mono">expected_fields</span>
                <span className="mono">{event.quality.expected_field_count}</span>
                <span className="muted mono">present_fields</span>
                <span className="mono">{event.quality.present_field_count}</span>
              </div>
              {event.quality.flags.length === 0 ? (
                <div className="muted" style={{ fontSize: 12 }}>
                  No flags. Clean run through all stages.
                </div>
              ) : (
                event.quality.flags.map((f, i) => (
                  <div
                    key={i}
                    className={cx("qflag", f.severity)}
                    style={{ marginBottom: 6 }}
                  >
                    <div className="qf-bar" />
                    <div>
                      <div className="qf-code">{f.code}</div>
                      <div className="qf-msg">{f.message}</div>
                      <div className="qf-meta">
                        stage = {f.stage} · severity = {f.severity}
                      </div>
                    </div>
                  </div>
                ))
              )}

              <div className="spacer-md" />
              <div className="eyebrow" style={{ marginBottom: 8 }}>
                Provenance
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "140px 1fr",
                  rowGap: 6,
                  fontSize: 12,
                }}
              >
                <span className="muted mono">adapter</span>
                <span className="mono">
                  {event.provenance.adapter} · v{event.provenance.adapter_version}
                </span>
                <span className="muted mono">subject_id</span>
                <span className="mono">{event.subject_id}</span>
                <span className="muted mono">parent_event_id</span>
                <span className="mono">{event.provenance.parent_event_id ?? "—"}</span>
                <span className="muted mono">ingested_at</span>
                <span className="mono">{event.provenance.ingested_at}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

"use client";

import { cx } from "@/lib/cx";
import type {
  AdapterEmitRule,
  Binding,
  EventType,
  Granularity,
  Severity,
} from "@/lib/types";

import PathPill from "../PathPill";

type EmitComponent = NonNullable<AdapterEmitRule["payload"]["components"]>[number];

interface Props {
  emit: AdapterEmitRule;
  onChange: (next: AdapterEmitRule) => void;
}

const TYPES: EventType[] = [
  "measurement",
  "observation",
  "survey",
  "event",
  "summary",
  "session",
];

const GRANULARITIES: Granularity[] = ["instant", "interval", "daily", "session", "unknown"];

const SEVERITIES: Severity[] = ["info", "warning", "error"];

export default function EmitEditor({ emit, onChange }: Props) {
  const updPayload = (patch: Partial<AdapterEmitRule["payload"]>) =>
    onChange({ ...emit, payload: { ...emit.payload, ...patch } });

  const addComp = () =>
    updPayload({
      components: [
        ...(emit.payload.components ?? []),
        { name: "newComp", value: { path: "" }, unit: null },
      ],
    });
  const updComp = (i: number, patch: Partial<EmitComponent>) => {
    const arr = [...(emit.payload.components ?? [])];
    arr[i] = { ...arr[i], ...patch };
    updPayload({ components: arr });
  };
  const rmComp = (i: number) =>
    updPayload({ components: (emit.payload.components ?? []).filter((_, j) => j !== i) });

  const flags = emit.quality?.flags ?? [];
  const setFlags = (next: typeof flags) =>
    onChange({ ...emit, quality: { flags: next } });

  const addFlag = () =>
    setFlags([
      ...flags,
      {
        code: "NEW_FLAG",
        severity: "info",
        stage: "structured",
        message: "",
      },
    ]);
  const updFlag = (i: number, patch: Partial<(typeof flags)[number]>) => {
    const arr = [...flags];
    arr[i] = { ...arr[i], ...patch };
    setFlags(arr);
  };
  const rmFlag = (i: number) => setFlags(flags.filter((_, j) => j !== i));

  return (
    <div>
      <div className="row">
        <div className="field">
          <label>id</label>
          <input
            className="input mono"
            value={emit.id}
            onChange={(e) => onChange({ ...emit, id: e.target.value })}
          />
        </div>
        <div className="field">
          <label>type</label>
          <select
            className="select"
            value={emit.type}
            onChange={(e) => onChange({ ...emit, type: e.target.value as EventType })}
          >
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>granularity</label>
          <select
            className="select"
            value={emit.granularity ?? "unknown"}
            onChange={(e) =>
              onChange({ ...emit, granularity: e.target.value as Granularity })
            }
          >
            {GRANULARITIES.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>category</label>
          {typeof emit.category === "string" ? (
            <input
              className="input mono"
              value={emit.category}
              onChange={(e) => onChange({ ...emit, category: e.target.value })}
            />
          ) : (
            <div>
              <PathPill binding={emit.category as Binding} />
            </div>
          )}
        </div>
      </div>

      <div className="spacer-sm" />
      <div className="field">
        <label>description</label>
        <input
          className="input"
          value={emit.description ?? ""}
          onChange={(e) => onChange({ ...emit, description: e.target.value })}
        />
      </div>

      {emit.iterate && (
        <>
          <div className="spacer-md" />
          <div className="field">
            <label>iterate · emits one event per array item</label>
            <div className="row">
              <input
                className="input mono"
                value={emit.iterate}
                onChange={(e) => onChange({ ...emit, iterate: e.target.value })}
              />
              <span className="chip accent" style={{ flex: 0 }}>
                @item
              </span>
            </div>
          </div>
        </>
      )}

      <div className="ascii-sep">— TIMESTAMP —</div>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="field">
          <label>start</label>
          <div>
            <PathPill binding={emit.timestamp.start} />
          </div>
        </div>
        {emit.timestamp.end && (
          <div className="field">
            <label>end</label>
            <div>
              <PathPill binding={emit.timestamp.end} />
            </div>
          </div>
        )}
        {emit.timestamp.duration_seconds != null && (
          <div className="field">
            <label>duration_seconds</label>
            <div>
              {typeof emit.timestamp.duration_seconds === "number" ? (
                <span className="chip mono">{emit.timestamp.duration_seconds}</span>
              ) : (
                <PathPill binding={emit.timestamp.duration_seconds} />
              )}
            </div>
          </div>
        )}
      </div>

      <div className="ascii-sep">— PAYLOAD —</div>
      <div className="row">
        <div className="field">
          <label>value</label>
          <div>
            <PathPill binding={emit.payload.value} />
          </div>
        </div>
        <div className="field">
          <label>raw_value</label>
          <div>
            <PathPill binding={emit.payload.raw_value} />
          </div>
        </div>
        <div className="field">
          <label>unit</label>
          <div>
            <PathPill binding={emit.payload.unit} />
          </div>
        </div>
        <div className="field">
          <label>label</label>
          <div>
            <PathPill binding={emit.payload.label} />
          </div>
        </div>
      </div>

      {(emit.payload.components?.length ?? 0) > 0 ? (
        <>
          <div className="spacer-md" />
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            Components
          </div>
          {(emit.payload.components ?? []).map((c, i) => (
            <div key={i} className="comp-row">
              <input
                className="input mono"
                value={c.name}
                onChange={(e) => updComp(i, { name: e.target.value })}
              />
              <div>
                <PathPill binding={c.value as Binding} />
              </div>
              <input
                className="input mono"
                value={c.unit ?? ""}
                placeholder="unit"
                onChange={(e) => updComp(i, { unit: e.target.value || null })}
              />
              <button className="btn ghost icon" onClick={() => rmComp(i)}>
                ×
              </button>
            </div>
          ))}
          <div style={{ marginTop: 8 }}>
            <button className="btn tiny" onClick={addComp}>
              + Add component
            </button>
          </div>
        </>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button className="btn tiny" onClick={addComp}>
            + Add components
          </button>
        </div>
      )}

      <div className="ascii-sep">— QUALITY FLAGS —</div>
      {flags.length === 0 && (
        <div className="empty" style={{ padding: "20px 0" }}>
          No adapter-declared quality flags. The validator and qualifier may still attach flags downstream.
        </div>
      )}
      {flags.map((f, i) => (
        <div key={i} className={cx("qflag", f.severity)} style={{ marginBottom: 8 }}>
          <div className="qf-bar" />
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                className="input mono qf-code"
                value={f.code ?? ""}
                style={{ flex: 0, width: 200 }}
                onChange={(e) => updFlag(i, { code: e.target.value })}
              />
              <select
                className="select"
                style={{ width: 110 }}
                value={f.severity ?? "info"}
                onChange={(e) =>
                  updFlag(i, { severity: e.target.value as Severity })
                }
              >
                {SEVERITIES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <span className="muted mono" style={{ fontSize: 10 }}>
                @stage={f.stage ?? "structured"}
              </span>
              <button
                className="btn ghost icon"
                onClick={() => rmFlag(i)}
                style={{ marginLeft: "auto" }}
              >
                ×
              </button>
            </div>
            <input
              className="input qf-msg"
              value={f.message ?? ""}
              placeholder="Human-readable message"
              onChange={(e) => updFlag(i, { message: e.target.value })}
              style={{ marginTop: 6 }}
            />
            {f.condition && (
              <div className="qf-meta" style={{ marginTop: 6 }}>
                when {f.condition.field}{" "}
                {f.condition.equals !== undefined
                  ? `equals ${JSON.stringify(f.condition.equals)}`
                  : ""}
              </div>
            )}
          </div>
        </div>
      ))}

      <div style={{ marginTop: 8 }}>
        <button className="btn tiny" onClick={addFlag}>
          + Add quality flag
        </button>
      </div>
    </div>
  );
}

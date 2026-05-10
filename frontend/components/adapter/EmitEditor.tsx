"use client";

import { cx } from "@/lib/cx";
import type {
  AdapterEmitRule,
  Binding,
  EventType,
  Granularity,
  Severity,
  Stage,
} from "@/lib/types";

import BindingInput from "./BindingInput";

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

const STAGES: Stage[] = [
  "raw",
  "structured",
  "cleaned",
  "validated",
  "qualified",
  "mapped",
  "standardized",
];

export default function EmitEditor({ emit, onChange }: Props) {
  const updPayload = (patch: Partial<AdapterEmitRule["payload"]>) =>
    onChange({ ...emit, payload: { ...emit.payload, ...patch } });

  const updTimestamp = (patch: Partial<AdapterEmitRule["timestamp"]>) =>
    onChange({ ...emit, timestamp: { ...emit.timestamp, ...patch } });

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

  // category can be a literal string or a Binding. Treat string as the simple
  // path. Toggle button below switches to a binding.
  const categoryIsString = typeof emit.category === "string";

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
          {categoryIsString ? (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                className="input mono"
                value={emit.category as string}
                onChange={(e) => onChange({ ...emit, category: e.target.value })}
              />
              <button
                className="btn tiny"
                title="Switch to a binding (path/template)"
                onClick={() => onChange({ ...emit, category: { path: "" } })}
              >
                →path
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <BindingInput
                value={emit.category}
                onChange={(b) => onChange({ ...emit, category: (b ?? "") as Binding })}
              />
              <button
                className="btn tiny"
                title="Switch to a literal string"
                onClick={() => onChange({ ...emit, category: "" })}
              >
                →literal
              </button>
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

      <div className="spacer-sm" />
      <div className="field">
        <label>iterate · emits one event per array item (leave blank if not iterating)</label>
        <div className="row" style={{ alignItems: "center" }}>
          <input
            className="input mono"
            value={emit.iterate ?? ""}
            placeholder="e.g. items"
            onChange={(e) => {
              const v = e.target.value;
              const next = { ...emit };
              if (v) next.iterate = v;
              else delete next.iterate;
              onChange(next);
            }}
          />
          <span className="chip accent" style={{ flex: 0 }}>
            @item
          </span>
        </div>
      </div>

      <div className="ascii-sep">— TIMESTAMP —</div>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="field" style={{ minWidth: 280 }}>
          <label>start</label>
          <BindingInput
            value={emit.timestamp.start}
            onChange={(b) => updTimestamp({ start: b })}
            placeholder="timestamp path"
          />
        </div>
        <div className="field" style={{ minWidth: 280 }}>
          <label>
            end
            {emit.timestamp.end == null && (
              <button
                className="btn tiny"
                style={{ marginLeft: 6 }}
                onClick={() => updTimestamp({ end: { path: "" } })}
              >
                + add
              </button>
            )}
          </label>
          {emit.timestamp.end != null && (
            <BindingInput
              value={emit.timestamp.end}
              removable
              onChange={(b) => {
                if (b === undefined) {
                  const next = { ...emit.timestamp };
                  delete next.end;
                  onChange({ ...emit, timestamp: next });
                } else {
                  updTimestamp({ end: b });
                }
              }}
            />
          )}
        </div>
        <div className="field" style={{ minWidth: 280 }}>
          <label>
            duration_seconds
            {emit.timestamp.duration_seconds == null && (
              <button
                className="btn tiny"
                style={{ marginLeft: 6 }}
                onClick={() => updTimestamp({ duration_seconds: 0 })}
              >
                + add
              </button>
            )}
          </label>
          {emit.timestamp.duration_seconds != null && (
            <BindingInput
              value={emit.timestamp.duration_seconds}
              removable
              onChange={(b) => {
                if (b === undefined) {
                  const next = { ...emit.timestamp };
                  delete next.duration_seconds;
                  onChange({ ...emit, timestamp: next });
                } else {
                  updTimestamp({ duration_seconds: b });
                }
              }}
            />
          )}
        </div>
      </div>

      <div className="ascii-sep">— PAYLOAD —</div>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="field" style={{ minWidth: 280 }}>
          <label>value</label>
          <BindingInput
            value={emit.payload.value}
            onChange={(b) => updPayload({ value: b })}
          />
        </div>
        <div className="field" style={{ minWidth: 280 }}>
          <label>raw_value</label>
          <BindingInput
            value={emit.payload.raw_value}
            onChange={(b) => updPayload({ raw_value: b })}
          />
        </div>
        <div className="field" style={{ minWidth: 280 }}>
          <label>unit</label>
          <BindingInput
            value={emit.payload.unit}
            onChange={(b) => updPayload({ unit: b })}
          />
        </div>
        <div className="field" style={{ minWidth: 280 }}>
          <label>label</label>
          <BindingInput
            value={emit.payload.label}
            onChange={(b) => updPayload({ label: b })}
          />
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
              <BindingInput
                value={c.value as Binding}
                onChange={(b) => updComp(i, { value: b })}
              />
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
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
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
              <label className="muted mono" style={{ fontSize: 10 }}>
                stage
              </label>
              <select
                className="select"
                style={{ width: 130, fontSize: 11 }}
                value={(f.stage as Stage) ?? "structured"}
                onChange={(e) => updFlag(i, { stage: e.target.value })}
              >
                {STAGES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
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
            <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              {f.condition ? (
                <>
                  <span className="muted mono" style={{ fontSize: 10 }}>
                    when
                  </span>
                  <input
                    className="input mono"
                    style={{ width: 160, padding: "3px 8px", fontSize: 11 }}
                    value={f.condition.field}
                    placeholder="field"
                    onChange={(e) =>
                      updFlag(i, {
                        condition: { ...f.condition!, field: e.target.value },
                      })
                    }
                  />
                  <span className="muted mono" style={{ fontSize: 10 }}>
                    equals
                  </span>
                  <input
                    className="input mono"
                    style={{ width: 160, padding: "3px 8px", fontSize: 11 }}
                    value={
                      f.condition.equals === undefined
                        ? ""
                        : typeof f.condition.equals === "string"
                          ? f.condition.equals
                          : JSON.stringify(f.condition.equals)
                    }
                    placeholder="value"
                    onChange={(e) =>
                      updFlag(i, {
                        condition: { ...f.condition!, equals: e.target.value },
                      })
                    }
                  />
                  <button
                    className="btn ghost icon"
                    title="Remove condition"
                    onClick={() => {
                      const arr = [...flags];
                      const next = { ...f };
                      delete next.condition;
                      arr[i] = next;
                      setFlags(arr);
                    }}
                  >
                    ×
                  </button>
                </>
              ) : (
                <button
                  className="btn tiny"
                  onClick={() =>
                    updFlag(i, { condition: { field: "", equals: "" } })
                  }
                >
                  + Add condition
                </button>
              )}
            </div>
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

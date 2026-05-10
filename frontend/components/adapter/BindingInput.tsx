"use client";

import type { Binding } from "@/lib/types";

type Mode = "path" | "literal" | "template" | "advanced";

interface Props {
  value: Binding | undefined;
  onChange: (next: Binding | undefined) => void;
  // Optional placeholder for the primary input when in path/literal/template mode.
  placeholder?: string;
  // If true, show a small "remove" button that calls onChange(undefined).
  removable?: boolean;
}

function detectMode(v: Binding | undefined): Mode {
  if (v === undefined || v === null) return "path";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return "literal";
  if ("template" in v && v.template !== undefined) return "template";
  if ("path" in v && v.path !== undefined) return "path";
  if ("lookup" in v || "multiply" in v || "date_from" in v || "time_from" in v) return "advanced";
  // Empty object — treat as path with empty string.
  return "path";
}

function isObjBinding(
  v: Binding | undefined,
): v is Exclude<Binding, string | number | boolean | null | undefined> {
  return typeof v === "object" && v !== null;
}

export default function BindingInput({ value, onChange, placeholder, removable }: Props) {
  const mode = detectMode(value);

  const setMode = (next: Mode) => {
    if (next === mode) return;
    if (next === "path") onChange({ path: "" });
    else if (next === "literal") onChange("");
    else if (next === "template") onChange({ template: "" });
    // advanced: leave as-is (user must edit via YAML)
  };

  if (mode === "advanced") {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span className="chip" title="Edit this binding in the YAML view">
          advanced (YAML only)
        </span>
        <select
          className="select"
          style={{ width: 110, padding: "3px 6px", fontSize: 11 }}
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
        >
          <option value="advanced">advanced</option>
          <option value="path">path</option>
          <option value="literal">literal</option>
          <option value="template">template</option>
        </select>
      </div>
    );
  }

  // path mode
  if (mode === "path") {
    const path = isObjBinding(value) && typeof value.path === "string" ? value.path : "";
    const transform =
      isObjBinding(value) && typeof value.transform === "string" ? value.transform : "";
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <select
          className="select"
          style={{ width: 90, padding: "3px 6px", fontSize: 11 }}
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
        >
          <option value="path">path</option>
          <option value="literal">literal</option>
          <option value="template">template</option>
        </select>
        <input
          className="input mono"
          style={{ flex: 1, minWidth: 140, padding: "3px 8px", fontSize: 11 }}
          value={path}
          placeholder={placeholder ?? "items[0].field"}
          onChange={(e) => {
            const next: Binding = { ...(isObjBinding(value) ? value : {}), path: e.target.value };
            if (!transform && next.transform === undefined) delete next.transform;
            onChange(next);
          }}
        />
        <input
          className="input mono"
          style={{ width: 110, padding: "3px 8px", fontSize: 11 }}
          value={transform}
          placeholder="transform"
          onChange={(e) => {
            const base = isObjBinding(value) ? { ...value } : {};
            base.path = path;
            const v = e.target.value;
            if (v) base.transform = v;
            else delete base.transform;
            onChange(base);
          }}
        />
        {removable && (
          <button className="btn ghost icon" onClick={() => onChange(undefined)} title="Remove">
            ×
          </button>
        )}
      </div>
    );
  }

  // literal mode
  if (mode === "literal") {
    const lit =
      typeof value === "string" || typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : "";
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <select
          className="select"
          style={{ width: 90, padding: "3px 6px", fontSize: 11 }}
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
        >
          <option value="path">path</option>
          <option value="literal">literal</option>
          <option value="template">template</option>
        </select>
        <input
          className="input mono"
          style={{ flex: 1, minWidth: 140, padding: "3px 8px", fontSize: 11 }}
          value={lit}
          placeholder={placeholder ?? "value"}
          onChange={(e) => {
            const raw = e.target.value;
            // Coerce simple literals: numeric, true/false; otherwise keep as string.
            if (raw === "") onChange("");
            else if (raw === "true") onChange(true);
            else if (raw === "false") onChange(false);
            else if (/^-?\d+(\.\d+)?$/.test(raw)) onChange(Number(raw));
            else onChange(raw);
          }}
        />
        {removable && (
          <button className="btn ghost icon" onClick={() => onChange(undefined)} title="Remove">
            ×
          </button>
        )}
      </div>
    );
  }

  // template mode
  const tpl = isObjBinding(value) && typeof value.template === "string" ? value.template : "";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <select
        className="select"
        style={{ width: 90, padding: "3px 6px", fontSize: 11 }}
        value={mode}
        onChange={(e) => setMode(e.target.value as Mode)}
      >
        <option value="path">path</option>
        <option value="literal">literal</option>
        <option value="template">template</option>
      </select>
      <input
        className="input mono"
        style={{ flex: 1, minWidth: 140, padding: "3px 8px", fontSize: 11 }}
        value={tpl}
        placeholder={placeholder ?? "{value} bpm"}
        onChange={(e) => onChange({ ...(isObjBinding(value) ? value : {}), template: e.target.value })}
      />
      {removable && (
        <button className="btn ghost icon" onClick={() => onChange(undefined)} title="Remove">
          ×
        </button>
      )}
    </div>
  );
}

"use client";

import type { DefaultsBlock, Modality, Stage } from "@/lib/types";

interface Props {
  defaults: DefaultsBlock;
  onChange: (next: DefaultsBlock) => void;
}

const MODALITIES: Modality[] = [
  "wearable",
  "scale",
  "survey",
  "sensor",
  "app",
  "game",
  "vr",
  "unknown",
];

type SmtBinding = NonNullable<NonNullable<DefaultsBlock["context"]>["source_measurement_type"]>;

function smtPath(value: SmtBinding | undefined): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.path ?? "";
}

export default function DefaultsEditor({ defaults, onChange }: Props) {
  const ctx = defaults.context ?? {};

  return (
    <div>
      <div className="field">
        <label>subject_id binding</label>
        <div className="row">
          <input
            className="input mono"
            value={defaults.subject_id?.path ?? ""}
            onChange={(e) =>
              onChange({ ...defaults, subject_id: { path: e.target.value } })
            }
          />
          <span className="chip" style={{ flex: 0 }}>
            path
          </span>
        </div>
      </div>

      <div className="spacer-md" />
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        Context
      </div>
      <div className="row">
        <div className="field">
          <label>source</label>
          <input
            className="input mono"
            value={ctx.source ?? ""}
            onChange={(e) =>
              onChange({ ...defaults, context: { ...ctx, source: e.target.value } })
            }
          />
        </div>
        <div className="field">
          <label>modality</label>
          <select
            className="select"
            value={ctx.modality ?? "unknown"}
            onChange={(e) =>
              onChange({
                ...defaults,
                context: { ...ctx, modality: e.target.value as Modality },
              })
            }
          >
            {MODALITIES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="spacer-sm" />
      <div className="field">
        <label>source_measurement_type</label>
        <input
          className="input mono"
          value={smtPath(ctx.source_measurement_type)}
          onChange={(e) =>
            onChange({
              ...defaults,
              context: {
                ...ctx,
                source_measurement_type: { path: e.target.value },
              },
            })
          }
        />
      </div>

      <div className="spacer-md" />
      <div className="field">
        <label>initial stage</label>
        <div>
          <span className="chip">{(defaults.stage as Stage) ?? "structured"}</span>
        </div>
      </div>
    </div>
  );
}

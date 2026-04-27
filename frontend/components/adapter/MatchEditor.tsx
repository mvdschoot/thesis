"use client";

import { cx } from "@/lib/cx";
import type { MatchBlock, MatchPredicate, PredicateOp } from "@/lib/types";

interface Props {
  match: MatchBlock;
  onChange: (next: MatchBlock) => void;
}

const OP_LABEL: Record<PredicateOp, string> = {
  equals: "equals",
  exists: "exists",
  type: "type",
  in: "in",
  non_empty: "non-empty",
};

const OP_CLASS: Record<PredicateOp, string> = {
  equals: "eq",
  exists: "ex",
  type: "ty",
  in: "in",
  non_empty: "ex",
};

const OP_OPTIONS: PredicateOp[] = ["equals", "exists", "type", "in", "non_empty"];

export default function MatchEditor({ match, onChange }: Props) {
  const update = (i: number, patch: Partial<MatchPredicate>) => {
    const copy = [...match.record];
    copy[i] = { ...copy[i], ...patch };
    onChange({ ...match, record: copy });
  };
  const remove = (i: number) => {
    onChange({ ...match, record: match.record.filter((_, j) => j !== i) });
  };
  const add = () => {
    onChange({
      ...match,
      record: [...match.record, { field: "newField", op: "exists", value: true }],
    });
  };

  const renderValue = (p: MatchPredicate) => {
    if (Array.isArray(p.value)) return p.value.join(",");
    return String(p.value);
  };

  return (
    <div>
      <div className="row" style={{ alignItems: "end", marginBottom: 12 }}>
        <div className="field">
          <label>source</label>
          <input
            className="input mono"
            value={match.source}
            onChange={(e) => onChange({ ...match, source: e.target.value })}
          />
        </div>
        <div style={{ flex: 0 }}>
          <div className="help" style={{ margin: 0 }}>
            Fires when an incoming record&apos;s <span className="mono">_metadata.source</span> equals this value.
          </div>
        </div>
      </div>

      <div className="eyebrow" style={{ marginBottom: 8 }}>
        Record predicates · ALL must pass
      </div>

      {match.record.map((p, i) => (
        <div key={i} className="predicate">
          <span className={cx("op", OP_CLASS[p.op])}>{OP_LABEL[p.op]}</span>
          <input
            className="input mono field-name"
            value={p.field}
            onChange={(e) => update(i, { field: e.target.value })}
            style={{ border: "none", padding: 0, background: "transparent" }}
          />
          <select
            className="select"
            style={{ width: 110, padding: "3px 6px", fontSize: 11 }}
            value={p.op}
            onChange={(e) => update(i, { op: e.target.value as PredicateOp })}
          >
            {OP_OPTIONS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
          <input
            className="input mono val"
            style={{ width: 140, padding: "3px 6px" }}
            value={renderValue(p)}
            onChange={(e) => update(i, { value: e.target.value })}
          />
          <button
            className="btn ghost icon x"
            onClick={() => remove(i)}
            title="Remove"
          >
            ×
          </button>
        </div>
      ))}

      <div style={{ marginTop: 10 }}>
        <button className="btn tiny" onClick={add}>
          + Add predicate
        </button>
      </div>
    </div>
  );
}

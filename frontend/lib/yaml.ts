// YAML <-> editor-shape conversion for adapter configs.
//
// The on-disk YAML uses verb-keyed predicates (`{ field: X, equals: Y }`).
// The visual editor wants `{ field, op, value }` so the predicate row can
// render with a single op selector. Anything else round-trips unchanged.

import yaml from "js-yaml";

import type {
  AdapterConfig,
  MatchPredicate,
  PredicateOp,
} from "./types";

const VERB_KEYS: PredicateOp[] = ["equals", "exists", "type", "in", "non_empty"];

interface DiskPredicate {
  field: string;
  equals?: unknown;
  exists?: boolean;
  type?: string;
  in?: unknown[];
  non_empty?: boolean;
}

function predicateFromDisk(p: DiskPredicate): MatchPredicate {
  for (const verb of VERB_KEYS) {
    if (verb in p) {
      return { field: p.field, op: verb, value: p[verb] as unknown };
    }
  }
  // Unknown verb — fall through with a sane default so the editor remains usable.
  return { field: p.field, op: "exists", value: true };
}

function predicateToDisk(p: MatchPredicate): DiskPredicate {
  // The editor stores `value` as whatever the user typed; coerce a few
  // common cases on the way out.
  let v: unknown = p.value;
  if (p.op === "exists" || p.op === "non_empty") {
    v = v === true || v === "true";
  } else if (p.op === "in" && typeof v === "string") {
    v = v
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return { field: p.field, [p.op]: v } as DiskPredicate;
}

export function parseAdapterYaml(text: string): AdapterConfig {
  const raw = yaml.load(text) as Record<string, unknown>;
  if (!raw || typeof raw !== "object") {
    throw new Error("YAML root must be a mapping");
  }
  const match = raw.match as { source: string; record?: DiskPredicate[] } | undefined;
  return {
    adapter: raw.adapter as AdapterConfig["adapter"],
    match: {
      source: match?.source ?? "",
      record: (match?.record ?? []).map(predicateFromDisk),
    },
    defaults: (raw.defaults ?? {}) as AdapterConfig["defaults"],
    emit: (raw.emit ?? []) as AdapterConfig["emit"],
  };
}

export function dumpAdapterYaml(config: AdapterConfig): string {
  const onDisk = {
    adapter: config.adapter,
    match: {
      source: config.match.source,
      record: config.match.record.map(predicateToDisk),
    },
    defaults: config.defaults,
    emit: config.emit,
  };
  return yaml.dump(onDisk, { lineWidth: 120, noRefs: true });
}

// Lightweight, render-only YAML serializer for object dumps in the UI. Keeps
// formatting predictable and avoids pulling js-yaml's dump path for small
// previews that don't need to round-trip.
export function yamlify(obj: unknown, indent = 0): string {
  const pad = "  ".repeat(indent);
  if (obj === null || obj === undefined) return "null";
  if (typeof obj === "string") return JSON.stringify(obj);
  if (typeof obj === "number" || typeof obj === "boolean") return String(obj);
  if (Array.isArray(obj)) {
    if (obj.length === 0) return "[]";
    return (
      "\n" +
      obj
        .map((item) => {
          const v = yamlify(item, indent + 1);
          if (v.startsWith("\n")) {
            return `${pad}-${v.replace(/^\n/, "\n" + pad + "  ").replace(/^/, " ")}`.replace(
              /\n {2}/,
              "\n  ",
            );
          }
          return `${pad}- ${v}`;
        })
        .join("\n")
    );
  }
  if (typeof obj === "object") {
    const o = obj as Record<string, unknown>;
    const keys = Object.keys(o);
    if (keys.length === 0) return "{}";
    return (
      (indent > 0 ? "\n" : "") +
      keys
        .map((k) => {
          const v = yamlify(o[k], indent + 1);
          if (v.startsWith("\n")) return `${pad}${k}:${v}`;
          return `${pad}${k}: ${v}`;
        })
        .join("\n")
    );
  }
  return String(obj);
}

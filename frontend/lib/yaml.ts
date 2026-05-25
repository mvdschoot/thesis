// YAML <-> editor-shape conversion for pipeline configs.
//
// The on-disk YAML uses verb-keyed predicates (`{ field: X, equals: Y }`).
// The visual editor wants `{ field, op, value }` so the predicate row can
// render with a single op selector. Anything else round-trips unchanged.
//
// Lossless round-trip: the parser stashes every top-level key it doesn't
// model explicitly (clean, validate, qualify, plus anything novel) so the
// dumper can re-emit them in the same place.

import yaml from "js-yaml";

import type {
  AdapterConfig,
  MatchPredicate,
  PipelineConfig,
  PredicateOp,
} from "./types";

const VERB_KEYS: PredicateOp[] = ["equals", "exists", "type", "in", "non_empty"];
const KNOWN_TOP_LEVEL_KEYS = new Set([
  "adapter",
  "match",
  "defaults",
  "emit",
  "clean",
  "validate",
  "qualify",
  "fhir",
  "omop",
]);

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

export function parseAdapterYaml(text: string): PipelineConfig {
  const raw = yaml.load(text) as Record<string, unknown>;
  if (!raw || typeof raw !== "object") {
    throw new Error("YAML root must be a mapping");
  }
  const match = raw.match as { source: string; record?: DiskPredicate[] } | undefined;
  const extra: Record<string, unknown> = {};
  for (const key of Object.keys(raw)) {
    if (!KNOWN_TOP_LEVEL_KEYS.has(key)) {
      extra[key] = raw[key];
    }
  }
  return {
    adapter: raw.adapter as PipelineConfig["adapter"],
    match: {
      source: match?.source ?? "",
      record: (match?.record ?? []).map(predicateFromDisk),
    },
    defaults: (raw.defaults ?? {}) as PipelineConfig["defaults"],
    emit: (raw.emit ?? []) as PipelineConfig["emit"],
    clean: raw.clean as Record<string, unknown> | undefined,
    validate: raw.validate as Record<string, unknown> | undefined,
    qualify: raw.qualify as Record<string, unknown> | undefined,
    fhir: raw.fhir as Record<string, unknown> | undefined,
    omop: raw.omop as Record<string, unknown> | undefined,
    extra: Object.keys(extra).length > 0 ? extra : undefined,
  };
}

export function dumpAdapterYaml(config: PipelineConfig): string {
  // Build the on-disk object key by key so the section order matches what the
  // backend's prompt teaches the LLM to emit (adapter → match → defaults →
  // emit → clean → validate → qualify). Optional sections are skipped when
  // unset so we don't write `clean: undefined`.
  const onDisk: Record<string, unknown> = {
    adapter: config.adapter,
    match: {
      source: config.match.source,
      record: config.match.record.map(predicateToDisk),
    },
    defaults: config.defaults,
    emit: config.emit,
  };
  if (config.clean !== undefined) onDisk.clean = config.clean;
  if (config.validate !== undefined) onDisk.validate = config.validate;
  if (config.qualify !== undefined) onDisk.qualify = config.qualify;
  if (config.fhir !== undefined) onDisk.fhir = config.fhir;
  if (config.omop !== undefined) onDisk.omop = config.omop;
  if (config.extra) {
    for (const [k, v] of Object.entries(config.extra)) {
      onDisk[k] = v;
    }
  }
  return yaml.dump(onDisk, { lineWidth: 120, noRefs: true, sortKeys: false });
}

/** @deprecated alias retained for callers still using the old type name. */
export type { AdapterConfig };


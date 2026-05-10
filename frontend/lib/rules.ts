// Read-only summaries of the cleaner / validator / qualifier blocks of a
// pipeline config, used by StageRulesPanel to render a static view of what
// will run. The backend is the source of truth for shape; we just project.

import type { PipelineConfig } from "./types";

export const CLEAN_NAMES = [
  "whitespace",
  "timestamp_normalizer",
  "type_coercer",
  "unit_inferrer",
] as const;

export const VALIDATE_NAMES = [
  "required_fields",
  "timestamp_window",
  "payload_shape",
  "unit_whitelist",
  "range",
] as const;

export const QUALIFY_NAMES = [
  "completeness",
  "duplicates",
  "outliers",
  "conformance",
  "plausibility",
] as const;

export interface RuleSummary {
  /** Canonical rule name from the closed enum. */
  name: string;
  /** Human-readable label. */
  label: string;
  /** Whether the rule will run for the active config. */
  enabled: boolean;
  /** Params bound on this rule (omitted when there are none). */
  params?: Record<string, unknown>;
}

const CLEAN_LABELS: Record<string, string> = {
  whitespace: "Whitespace strip",
  timestamp_normalizer: "Timestamp normalize",
  type_coercer: "Type coercion",
  unit_inferrer: "Unit inference",
};

const VALIDATE_LABELS: Record<string, string> = {
  required_fields: "Required fields",
  timestamp_window: "Timestamp window",
  payload_shape: "Payload shape",
  unit_whitelist: "Unit whitelist",
  range: "Range check",
};

const QUALIFY_LABELS: Record<string, string> = {
  completeness: "Completeness ratio",
  duplicates: "Duplicate fingerprint",
  outliers: "Hampel outlier",
  conformance: "Conformance derivation",
  plausibility: "Plausibility derivation",
};

function readArray(v: unknown): unknown[] | null {
  return Array.isArray(v) ? v : null;
}

function readObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

export function summarizeClean(config: PipelineConfig | null): RuleSummary[] {
  const block = readObject(config?.clean);
  const heuristics = readArray(block?.heuristics);
  // No `clean` block (or no `heuristics`) → backend runs the default chain
  // with no params. Mirror that here.
  if (!heuristics) {
    return CLEAN_NAMES.map((name) => ({
      name,
      label: CLEAN_LABELS[name],
      enabled: true,
    }));
  }
  const enabledMap = new Map<string, Record<string, unknown>>();
  for (const entry of heuristics) {
    if (typeof entry === "string") {
      enabledMap.set(entry, {});
    } else if (entry && typeof entry === "object" && "name" in entry) {
      const obj = entry as Record<string, unknown>;
      const { name, ...rest } = obj as { name: string } & Record<string, unknown>;
      enabledMap.set(name, rest);
    }
  }
  return CLEAN_NAMES.map((name) => {
    const params = enabledMap.get(name);
    return {
      name,
      label: CLEAN_LABELS[name],
      enabled: params !== undefined,
      params: params && Object.keys(params).length > 0 ? params : undefined,
    };
  });
}

export function summarizeValidate(config: PipelineConfig | null): RuleSummary[] {
  const block = readObject(config?.validate);
  const enabledList = readArray(block?.enabled);
  const enabled = enabledList ? new Set(enabledList as string[]) : null;
  const tsWindow = readObject(block?.timestamp_window);
  const categories = readObject(block?.categories);
  return VALIDATE_NAMES.map((name) => {
    const isOn = enabled === null ? true : enabled.has(name);
    let params: Record<string, unknown> | undefined;
    if (name === "timestamp_window" && tsWindow) {
      params = tsWindow;
    } else if (
      (name === "unit_whitelist" || name === "range") &&
      categories &&
      Object.keys(categories).length > 0
    ) {
      params = { categories };
    }
    return { name, label: VALIDATE_LABELS[name], enabled: isOn, params };
  });
}

export function summarizeQualify(config: PipelineConfig | null): RuleSummary[] {
  const block = readObject(config?.qualify);
  const enabledList = readArray(block?.enabled);
  const enabled = enabledList ? new Set(enabledList as string[]) : null;
  const outliers = readObject(block?.outliers);
  const duplicates = readObject(block?.duplicates);
  const plausibility = readObject(block?.plausibility);
  const completeness = readObject(block?.completeness);
  return QUALIFY_NAMES.map((name) => {
    const isOn = enabled === null ? true : enabled.has(name);
    let params: Record<string, unknown> | undefined;
    if (name === "outliers" && outliers) params = outliers;
    if (name === "duplicates" && duplicates) params = duplicates;
    if (name === "plausibility" && plausibility) params = plausibility;
    if (name === "completeness" && completeness) params = completeness;
    return { name, label: QUALIFY_LABELS[name], enabled: isOn, params };
  });
}

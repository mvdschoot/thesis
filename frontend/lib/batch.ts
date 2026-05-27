import type {
  TransformResponse,
  TransformFormat,
  TransformStats,
  AdapterDiagnostics,
  RuleDiagnostic,
  SkippedReason,
} from "./api";
import type {
  CanonicalEvent,
  ConceptSlot,
  FhirBundle,
  FhirBundleEntry,
  OmopCdmOutput,
} from "./types";

const BATCH_RECORD_LIMIT = 2000;
const BATCH_BYTE_LIMIT = 8 * 1024 * 1024;
const SKIP_BATCH_THRESHOLD_RECORDS = 1000;
const SKIP_BATCH_THRESHOLD_BYTES = 4 * 1024 * 1024;
export const MATCH_SAMPLE_SIZE = 50;

export interface BatchChunk {
  data: unknown;
  index: number;
  recordCount: number;
}

export interface BatchProgress {
  batchIndex: number;
  batchCount: number;
  eventsProcessed: number;
  status: "pending" | "running" | "done" | "error";
  error?: string;
}

function countRecords(data: unknown, format: TransformFormat): number {
  if (format === "csv") {
    const text = data as string;
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    return Math.max(0, lines.length - 1); // subtract header
  }
  if (Array.isArray(data)) return data.length;
  return 1;
}

function byteSize(data: unknown, format: TransformFormat): number {
  if (format === "csv") return (data as string).length;
  return JSON.stringify(data).length;
}

export function needsBatching(data: unknown, format: TransformFormat): boolean {
  const records = countRecords(data, format);
  if (records <= SKIP_BATCH_THRESHOLD_RECORDS) return false;
  const bytes = byteSize(data, format);
  if (bytes <= SKIP_BATCH_THRESHOLD_BYTES) return false;
  return true;
}

export function splitIntoBatches(
  data: unknown,
  format: TransformFormat,
): BatchChunk[] {
  if (!needsBatching(data, format)) {
    return [{ data, index: 0, recordCount: countRecords(data, format) }];
  }

  if (format === "csv") return splitCsv(data as string);
  if (Array.isArray(data)) return splitJsonArray(data);
  return [{ data, index: 0, recordCount: 1 }];
}

function splitCsv(text: string): BatchChunk[] {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const lines = text.split(/\r?\n/);
  const header = lines[0] ?? "";
  const dataLines = lines.slice(1).filter((l) => l.trim() !== "");

  const chunks: BatchChunk[] = [];
  let limit = BATCH_RECORD_LIMIT;

  for (let i = 0; i < dataLines.length; ) {
    const slice = dataLines.slice(i, i + limit);
    const csvChunk = header + "\n" + slice.join("\n");

    if (csvChunk.length > BATCH_BYTE_LIMIT && limit > 50) {
      limit = Math.floor(limit / 2);
      continue;
    }

    chunks.push({ data: csvChunk, index: chunks.length, recordCount: slice.length });
    i += slice.length;
    limit = BATCH_RECORD_LIMIT;
  }

  return chunks;
}

function splitJsonArray(arr: unknown[]): BatchChunk[] {
  const chunks: BatchChunk[] = [];
  let limit = BATCH_RECORD_LIMIT;

  for (let i = 0; i < arr.length; ) {
    const slice = arr.slice(i, i + limit);
    const jsonSize = JSON.stringify(slice).length;

    if (jsonSize > BATCH_BYTE_LIMIT && limit > 50) {
      limit = Math.floor(limit / 2);
      continue;
    }

    chunks.push({ data: slice, index: chunks.length, recordCount: slice.length });
    i += slice.length;
    limit = BATCH_RECORD_LIMIT;
  }

  return chunks;
}

export function sampleForMatch(
  data: unknown,
  text: string,
  format: TransformFormat,
  maxRecords: number = MATCH_SAMPLE_SIZE,
): string {
  if (format === "csv") {
    const lines = text.split(/\r?\n/);
    const header = lines[0] ?? "";
    const dataLines = lines.slice(1).filter((l) => l.trim() !== "");
    if (dataLines.length <= maxRecords) return text;
    return header + "\n" + dataLines.slice(0, maxRecords).join("\n");
  }

  if (Array.isArray(data) && data.length > maxRecords) {
    return JSON.stringify(data.slice(0, maxRecords));
  }

  return text;
}

// ── Response merging ──────────────────────────────────────────────────────────

export function mergeResponses(responses: TransformResponse[]): TransformResponse {
  if (responses.length === 0) {
    return {
      events: [],
      stats: { count: 0, subjects: [], flags: {} },
      bundle: null,
      omop_cdm: null,
      concept_slots: [],
      adapter_diagnostics: null,
    };
  }
  if (responses.length === 1) return responses[0];

  return {
    events: mergeEvents(responses),
    stats: mergeStats(responses),
    bundle: mergeBundles(responses),
    omop_cdm: mergeOmop(responses),
    concept_slots: mergeConceptSlots(responses),
    adapter_diagnostics: mergeDiagnostics(responses),
  };
}

function mergeEvents(responses: TransformResponse[]): CanonicalEvent[] {
  const all: CanonicalEvent[] = [];
  for (const r of responses) all.push(...r.events);
  return all;
}

function sumRecords(
  target: Record<string, number>,
  source: Record<string, number> | undefined,
): void {
  if (!source) return;
  for (const [k, v] of Object.entries(source)) {
    target[k] = (target[k] ?? 0) + v;
  }
}

function mergeStats(responses: TransformResponse[]): TransformStats {
  const merged: TransformStats = {
    count: 0,
    subjects: [],
    flags: {},
    severity: {},
    stages: {},
    plausibility: {},
    conformance: {},
  };

  const subjectSet = new Set<string>();

  for (const r of responses) {
    merged.count += r.stats.count;
    for (const s of r.stats.subjects) subjectSet.add(s);
    sumRecords(merged.flags, r.stats.flags);
    sumRecords(merged.severity!, r.stats.severity);
    sumRecords(merged.stages!, r.stats.stages);
    sumRecords(merged.plausibility!, r.stats.plausibility);
    sumRecords(merged.conformance!, r.stats.conformance);
  }

  merged.subjects = Array.from(subjectSet);
  return merged;
}

function mergeBundles(responses: TransformResponse[]): FhirBundle | null {
  const bundles = responses.map((r) => r.bundle).filter((b): b is FhirBundle => b != null);
  if (bundles.length === 0) return null;
  if (bundles.length === 1) return bundles[0];

  const seen = new Set<string>();
  const entries: FhirBundleEntry[] = [];

  for (const b of bundles) {
    for (const entry of b.entry) {
      if (seen.has(entry.fullUrl)) continue;
      seen.add(entry.fullUrl);
      entries.push(entry);
    }
  }

  return {
    resourceType: "Bundle",
    type: bundles[0].type,
    entry: entries,
  };
}

function mergeOmop(responses: TransformResponse[]): OmopCdmOutput | null {
  const outputs = responses.map((r) => r.omop_cdm).filter((o): o is OmopCdmOutput => o != null);
  if (outputs.length === 0) return null;
  if (outputs.length === 1) return outputs[0];

  const personSeen = new Set<unknown>();
  const person: Record<string, unknown>[] = [];
  const measurement: Record<string, unknown>[] = [];
  const observation: Record<string, unknown>[] = [];
  const device_exposure: Record<string, unknown>[] = [];
  const observation_period: Record<string, unknown>[] = [];
  const unmapped: Record<string, unknown>[] = [];

  const resolution_stats = { total_codings: 0, resolved: 0, failed: 0, mapping_types: {} as Record<string, number> };

  for (const o of outputs) {
    for (const p of o.person) {
      const pid = p.person_id;
      if (personSeen.has(pid)) continue;
      personSeen.add(pid);
      person.push(p);
    }
    measurement.push(...o.measurement);
    observation.push(...o.observation);
    device_exposure.push(...o.device_exposure);
    unmapped.push(...o.unmapped);

    resolution_stats.total_codings += o.resolution_stats.total_codings;
    resolution_stats.resolved += o.resolution_stats.resolved;
    resolution_stats.failed += o.resolution_stats.failed;
    sumRecords(resolution_stats.mapping_types, o.resolution_stats.mapping_types);
  }

  // Deduplicate observation_period by (person_id, start, end)
  const opSeen = new Set<string>();
  for (const o of outputs) {
    for (const op of o.observation_period) {
      const key = `${op.person_id}|${op.observation_period_start_date}|${op.observation_period_end_date}`;
      if (opSeen.has(key)) continue;
      opSeen.add(key);
      observation_period.push(op);
    }
  }

  return {
    person,
    measurement,
    observation,
    device_exposure,
    observation_period,
    unmapped,
    resolution_stats,
    stats: {
      person_count: person.length,
      measurement_count: measurement.length,
      observation_count: observation.length,
      device_exposure_count: device_exposure.length,
      observation_period_count: observation_period.length,
      unmapped_count: unmapped.length,
      component_rows: outputs.reduce((s, o) => s + o.stats.component_rows, 0),
    },
  };
}

function mergeConceptSlots(responses: TransformResponse[]): ConceptSlot[] {
  const map = new Map<string, ConceptSlot>();

  for (const r of responses) {
    for (const slot of r.concept_slots) {
      const existing = map.get(slot.key);
      if (existing) {
        existing.count += slot.count;
        if (!existing.default_coding && slot.default_coding) {
          existing.default_coding = slot.default_coding;
        }
        if (!existing.current_mapping && slot.current_mapping) {
          existing.current_mapping = slot.current_mapping;
        }
      } else {
        map.set(slot.key, { ...slot });
      }
    }
  }

  return Array.from(map.values());
}

const MAX_SKIPPED_REASONS = 20;
const MAX_PREDICATE_FAILURES = 5;

function mergeDiagnostics(responses: TransformResponse[]): AdapterDiagnostics | null {
  const diags = responses
    .map((r) => r.adapter_diagnostics)
    .filter((d): d is AdapterDiagnostics => d != null);
  if (diags.length === 0) return null;
  if (diags.length === 1) return diags[0];

  const merged: AdapterDiagnostics = {
    records_total: 0,
    records_matched: 0,
    records_unmatched: 0,
    events_emitted: 0,
    rules: [],
    predicate_failures: [],
  };

  const ruleMap = new Map<string, RuleDiagnostic>();

  for (const d of diags) {
    merged.records_total += d.records_total;
    merged.records_matched += d.records_matched;
    merged.records_unmatched += d.records_unmatched;
    merged.events_emitted += d.events_emitted;

    for (const rule of d.rules) {
      const existing = ruleMap.get(rule.rule_id);
      if (existing) {
        existing.records_seen += rule.records_seen;
        existing.events_emitted += rule.events_emitted;
        const remaining = MAX_SKIPPED_REASONS - existing.skipped_reasons.length;
        if (remaining > 0) {
          existing.skipped_reasons.push(...rule.skipped_reasons.slice(0, remaining));
        }
      } else {
        ruleMap.set(rule.rule_id, {
          ...rule,
          skipped_reasons: rule.skipped_reasons.slice(0, MAX_SKIPPED_REASONS),
        });
      }
    }

    const predRemaining = MAX_PREDICATE_FAILURES - merged.predicate_failures.length;
    if (predRemaining > 0) {
      merged.predicate_failures.push(...d.predicate_failures.slice(0, predRemaining));
    }
  }

  merged.rules = Array.from(ruleMap.values());
  return merged;
}

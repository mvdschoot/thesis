"use client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const init: RequestInit = { method, headers: { "Content-Type": "application/json" }, signal };
  if (body !== undefined) init.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, "POST", body, signal);
}

function get<T>(path: string): Promise<T> {
  return request<T>(path, "GET");
}

function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, "PUT", body);
}

export interface GenerateConfigRequest {
  data: unknown;
  description: string;
  hints?: string;
  source?: string;
}

export interface GenerateConfigResponse {
  id: string;
  yaml: string;
}

export type RecordFilter = Record<string, unknown>;

export interface ConfigSummary {
  id: string;
  version?: string | null;
  description?: string | null;
  source?: string | null;
  record_filters: RecordFilter[];
}

export interface ConfigPayload {
  id: string;
  yaml: string;
}

export interface ConfigMatch {
  id: string;
  adapter: {
    id?: string | null;
    description?: string | null;
    version?: string | null;
  };
  source?: string | null;
  source_match: boolean;
  source_match_known: boolean;
  matched_records: number;
  total_records: number;
  applicable: boolean;
  error?: string | null;
}

export type TransformFormat = "json" | "csv";

export interface TransformRequest {
  data: unknown;
  yaml: string;
  source?: string;
  device?: string;
  format?: TransformFormat;
  concept_mappings?: Record<string, import("./types").Coding>;
}

export interface TransformStats {
  count: number;
  subjects: string[];
  flags: Record<string, number>;
  severity?: Record<string, number>;
  stages?: Record<string, number>;
  plausibility?: Record<string, number>;
  conformance?: Record<string, number>;
}

export interface SkippedReason {
  code: string;
  record_index: number;
  detail: string;
  rule_id: string | null;
  path: string | null;
  expected: unknown;
  actual: unknown;
  record_keys: string[] | null;
}

export interface RuleDiagnostic {
  rule_id: string;
  records_seen: number;
  events_emitted: number;
  skipped_reasons: SkippedReason[];
}

export interface AdapterDiagnostics {
  records_total: number;
  records_matched: number;
  records_unmatched: number;
  events_emitted: number;
  rules: RuleDiagnostic[];
  predicate_failures: SkippedReason[];
}

export interface TransformResponse {
  events: import("./types").CanonicalEvent[];
  stats: TransformStats;
  bundle: import("./types").FhirBundle | null;
  omop_cdm: import("./types").OmopCdmOutput | null;
  concept_slots: import("./types").ConceptSlot[];
  adapter_diagnostics?: AdapterDiagnostics | null;
}

export interface SuggestFixRequest {
  yaml: string;
  diagnostics: AdapterDiagnostics;
  sample_record: unknown;
  description?: string;
}

export interface SuggestFixResponse {
  yaml: string;
}

export type TerminologySystem = "loinc" | "ucum" | "snomed" | "rxnorm" | "icd10" | "cpt";

export function generateConfig(req: GenerateConfigRequest) {
  return post<GenerateConfigResponse>("/api/generate-config", req);
}

export function transform(req: TransformRequest, signal?: AbortSignal) {
  return post<TransformResponse>("/api/transform", req, signal);
}

export function suggestConfigFix(req: SuggestFixRequest) {
  return post<SuggestFixResponse>("/api/suggest-config-fix", req);
}

export function listConfigs() {
  return get<ConfigSummary[]>("/api/configs");
}

export function getConfig(id: string) {
  return get<ConfigPayload>(`/api/configs/${encodeURIComponent(id)}`);
}

export function updateConfig(id: string, yaml: string) {
  return put<ConfigPayload>(`/api/configs/${encodeURIComponent(id)}`, { yaml });
}

export function matchConfigs(data: string, format: TransformFormat, source?: string) {
  return post<ConfigMatch[]>("/api/configs/match", { data, format, source });
}

export interface NoMatchSlot {
  reason: string;
}

export interface SuggestConceptsResponse {
  suggestions: Record<string, import("./types").Coding>;
  no_matches: Record<string, NoMatchSlot>;
  errors: string[];
}

export function suggestConcepts(slots: import("./types").ConceptSlot[]) {
  return post<SuggestConceptsResponse>("/api/suggest-concepts", { slots });
}

export function searchTerminology(
  system: TerminologySystem,
  q: string,
  max: number = 20,
) {
  const params = new URLSearchParams({ system, q, max: String(max) });
  return get<import("./types").Coding[]>(`/api/terminology/search?${params}`);
}

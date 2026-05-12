// Domain types mirrored from backend/src/models/canonical.py.

export type Severity = "info" | "warning" | "error";

export type Plausibility = "ok" | "review" | "exclude";

export type Stage =
  | "raw"
  | "structured"
  | "cleaned"
  | "validated"
  | "qualified"
  | "mapped"
  | "standardized";

export type EventType =
  | "measurement"
  | "observation"
  | "survey"
  | "event"
  | "summary"
  | "session";

export type Granularity = "instant" | "interval" | "daily" | "session" | "unknown";

export type Modality =
  | "wearable"
  | "scale"
  | "survey"
  | "sensor"
  | "app"
  | "game"
  | "vr"
  | "unknown";

export interface QualityFlag {
  code: string;
  severity: Severity;
  stage: string;
  message?: string | null;
}

export interface PayloadComponent {
  name: string;
  value: unknown;
  unit?: string | null;
}

export interface Payload {
  raw_value: unknown;
  value: unknown;
  unit: string | null;
  label: string | null;
  components: PayloadComponent[] | null;
}

export interface Context {
  source: string;
  modality: Modality;
  device: string | null;
  source_measurement_type: string | null;
}

export interface Provenance {
  source_record_id: string | null;
  ingested_at: string;
  group_id: string | null;
  parent_event_id: string | null;
  adapter: string | null;
  adapter_version: string | null;
}

export interface Mapping {
  standard_code: string | null;
  standard_system: string | null;
  standard_display: string | null;
  confidence: number | null;
  method: string | null;
}

export interface Quality {
  flags: QualityFlag[];
  conformance: string | null;
  completeness: number | null;
  plausibility: Plausibility | null;
  expected_field_count: number | null;
  present_field_count: number | null;
}

export interface CanonicalEvent {
  event_id: string;
  subject_id: string;
  timestamp: string;
  timestamp_end: string | null;
  duration_seconds: number | null;
  type: EventType;
  category: string;
  granularity: Granularity;
  payload: Payload;
  context: Context;
  provenance: Provenance;
  mapping: Mapping;
  quality: Quality;
  stage: Stage;
  extensions: Record<string, unknown> | null;
  // Convenience field used by the frontend to colour-code by emit rule.
  emit_id?: string;
}

// ─── Adapter config (editor-friendly shape) ─────────────────────────────────
//
// The YAML on disk uses verb-keyed predicates (`{ field: X, equals: Y }`).
// The visual editor is easier to write against a flat `{ field, op, value }`
// shape; lib/yaml.ts converts between the two.

export type PredicateOp = "equals" | "exists" | "type" | "in" | "non_empty";

export interface MatchPredicate {
  field: string;
  op: PredicateOp;
  value: unknown;
}

export interface MatchBlock {
  source: string;
  record: MatchPredicate[];
}

export type Binding =
  | string
  | number
  | boolean
  | null
  | {
      path?: string;
      transform?: string;
      fallback?: Binding;
      template?: string;
      lookup?: unknown;
      multiply?: Binding[];
      date_from?: Binding;
      time_from?: Binding;
    };

export interface DefaultsBlock {
  subject_id?: { path?: string };
  context?: {
    source?: string;
    modality?: Modality;
    device?: string | null;
    source_measurement_type?: { path?: string } | string;
  };
  stage?: Stage;
  source_record_id?: Binding;
}

export interface AdapterEmitRule {
  id: string;
  description?: string;
  type: EventType;
  category: Binding;
  granularity?: Granularity;
  iterate?: string;
  parent?: string;
  timestamp: {
    start?: Binding;
    end?: Binding;
    duration_seconds?: Binding;
    date_from?: Binding;
    time_from?: Binding;
  };
  payload: {
    value?: Binding;
    raw_value?: Binding;
    unit?: Binding;
    label?: Binding;
    components?: Array<{ name: string; value?: Binding; unit?: string | null }>;
  };
  extensions?: Record<string, Binding>;
  quality?: {
    flags?: Array<
      Partial<QualityFlag> & {
        condition?: { field: string; equals?: unknown };
      }
    >;
  };
  quality_overrides?: Record<string, unknown>;
}

export interface PipelineConfig {
  adapter: { id: string; version: string; description?: string };
  match: MatchBlock;
  defaults: DefaultsBlock;
  emit: AdapterEmitRule[];
  // Optional stage-config blocks. Treated as opaque on the frontend — the
  // backend is the source of truth for their shape. The editor preserves
  // them losslessly through round-trip and the StageRulesPanel renders a
  // read-only summary view sourced from them.
  clean?: Record<string, unknown>;
  validate?: Record<string, unknown>;
  qualify?: Record<string, unknown>;
  fhir?: Record<string, unknown>;
  // Carry every other top-level YAML key the user (or LLM) included that we
  // don't model explicitly — keeps round-trip lossless.
  extra?: Record<string, unknown>;
}

/** @deprecated Use PipelineConfig. Kept as an alias during the transition. */
export type AdapterConfig = PipelineConfig;

// ─── FHIR Bundle (output-side, structural-only) ─────────────────────────────
//
// Minimal shape the frontend needs to render a Bundle viewer. We intentionally
// keep this loose — `resource` is `Record<string, unknown>` because text-only
// CodeableConcepts (no codings) and the variety of FHIR resource shapes don't
// repay a full type tree on the frontend. Backend is the source of truth.

export interface FhirBundleEntry {
  fullUrl: string;
  resource: { resourceType: string } & Record<string, unknown>;
  request?: { method: string; url: string };
}

export interface FhirBundle {
  resourceType: "Bundle";
  type: string;
  entry: FhirBundleEntry[];
}

// ─── Sample dataset shape (input-side mock) ─────────────────────────────────

export interface SampleDataset {
  label: string;
  source: string;
  file: string;
  record: unknown;
}

// Frontend visualization of the per-stage rules. Toggling these does NOT
// change pipeline behaviour today — the backend always runs its full default
// chain. They exist so the UI can show *which* rules each stage has.

import type { RuleToggle } from "./types";

export const CLEANER_RULES: RuleToggle[] = [
  { id: "whitespace", name: "Whitespace strip", desc: "Trim leading/trailing whitespace from string fields", on: true },
  { id: "timestamp", name: "Timestamp normalize", desc: "Coerce to ISO-8601 millisecond UTC", on: true },
  { id: "type-coerce", name: "Type coercion", desc: "Numeric strings → numbers; boolean strings → booleans", on: true },
  { id: "unit-infer", name: "Unit inference", desc: "Fill missing units from category default", on: true },
];

export const VALIDATOR_RULES: RuleToggle[] = [
  { id: "required-fields", name: "Required fields", desc: "expected_fields from quality_rules.yaml must be present", on: true },
  { id: "timestamp-window", name: "Timestamp window", desc: "Must fall in [2000-01-01, now+1d]", on: true },
  { id: "payload-shape", name: "Payload shape", desc: "value/raw_value/unit/label types match category", on: true },
  { id: "unit-whitelist", name: "Unit whitelist", desc: "payload.unit ∈ unit_whitelist for category", on: true },
  { id: "range", name: "Range check", desc: "payload.value within [min, max] per category", on: true },
];

export const QUALIFIER_RULES: RuleToggle[] = [
  { id: "completeness", name: "Completeness ratio", desc: "present_field_count / expected_field_count", on: true },
  { id: "duplicates", name: "Duplicate fingerprint", desc: "Hash (subject_id, timestamp, category, value)", on: true },
  { id: "outliers", name: "Hampel outlier", desc: "median ± 3.5·MAD per (subject_id, category), min n=5", on: true },
  { id: "conformance", name: "Conformance derivation", desc: "ok if no ERROR flags, else issues", on: true },
  { id: "plausibility", name: "Plausibility derivation", desc: "ok / review (≥1 warning) / exclude (any error)", on: true },
];

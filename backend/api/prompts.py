from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# api/prompts.py → backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_EXAMPLES_DIR = BACKEND_DIR / "configs" / "examples"
CANONICAL_MODEL_PATH = BACKEND_DIR / "domain" / "models.py"

FEW_SHOT_FILES = ["withings-body-scale.yaml", "fitabase-fitbit-csv.yaml"]

MAX_SAMPLE_BYTES = 20_000


DSL_OVERVIEW = """\
YAML DSL summary:

Top-level sections:
- `adapter`: { id, version, description } — identifies this config.
- `match`: { source, record? } — defines which records this config will handle.
  - `source` MUST equal the request's source_name (string equality).
  - `record` is an optional list of predicate entries, implicitly AND-ed. Each entry has a `field` (dot-path, supports `[index]`) and one or more verbs (AND-ed within the entry):
      - `equals: X`            — exact equality
      - `in: [A, B, C]`        — value ∈ list
      - `exists: true | false` — true: value is not null / present; false: value is null or missing
      - `type: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null"`
      - `non_empty: true`      — arrays/strings/objects must have length > 0
- `defaults` (optional): { subject_id, context, stage, source_record_id } — applied to every emitted event.
- `emit`: a list of rules. Each rule produces 0..n events per input record.
- `clean` (optional): cleaner chain composition + per-heuristic params. Omitted → default chain.
- `validate` (optional): which validators run + per-category overlay on top of the global quality_rules.yaml. Omitted → all validators, global rules.
- `qualify` (optional): which cross-event checks run + tunables (Hampel k, fingerprint fields, plausibility threshold). Omitted → all checks with defaults.
- `fhir` (optional): toggles + bundle shape for the FHIR R4 output stage. Omitted → FHIR output enabled with sensible defaults (Patient + Observation, transaction bundle).
- `omop` (optional): toggles + table selection for the OMOP CDM v5.4 output. Omitted → OMOP CDM output enabled with sensible defaults (all tables).

Match-block rigidity (MANDATORY):
- Do NOT rely on `match.source` alone — that lets the engine try to transform records you can't actually handle. For every config you generate, the `record` list MUST:
  1. Assert `exists: true` on every field the `defaults` block reads (subject_id source path, source_record_id template fields, timestamps).
  2. Assert `type: "array", non_empty: true` on every path used as an `iterate` target in the `emit` rules.
  3. Assert `type: "object"` on every intermediate container your emit paths walk through before reaching a leaf.
  4. Pin any discriminator field (e.g. `dataType`, `measurementType`, `recordKind`) with `equals` or `in` to the exact value(s) this config is designed for. If the same source emits multiple record kinds, use `in: [...]` enumerating only the kinds this config handles.
- A match block that would accept a garbage record is a bug. Prefer overly strict criteria; false positives produce unusable events, false negatives are surfaced as "no config matches" in the UI so the user can widen them.

Value-spec forms (use anywhere a value is needed):
- literal: `"foo"`, `42`, `null`
- path: `{ path: "some.nested.key" }` — dot notation, supports `[0]` indexing. Prefix `@item.` inside an iterated rule to reference the current iteration element. Use `{ path: "@record_index" }` to get the 0-based row/record number — useful as a stable subject_id when records have no explicit person identifier (e.g. `{ template: "respondent:{@record_index}" }`).
- transform: `{ path: "...", transform: "start_of_day" | "end_of_day" | "iso_date" | "iso_millis" | "to_int" | "to_float" }`
- fallback: `{ path: "...", fallback: <another-spec> }` — the fallback is itself a full value-spec (recursive).
- template: `{ template: "literal {path.to.field} more {@item.foo}" }` — brace-interpolation.
- composite timestamp: `{ date_from: <spec>, time_from: <spec> }` → produces `YYYY-MM-DDTHH:MM:SS.sssZ`.
- explicit timestamp parsing: `{ path: "...", parse_timestamp: "<strptime-format>" }` — parses the value with Python's `datetime.strptime` (e.g. `"%m/%d/%Y %I:%M:%S %p"` for `"3/12/2016 2:00:00 AM"`) and emits ISO 8601 in UTC. Naive timestamps are assumed UTC; aware timestamps are converted. Combinable with `template:` to merge separate date and time columns: `{ template: "{ActivityDate} {ActivityTime}", parse_timestamp: "%m/%d/%Y %I:%M:%S %p" }`.
- arithmetic: `{ multiply: [<spec>, <spec>, ...] }`.
- lookup table: `{ lookup: { key: <spec>, map: { "k1": "v1", ... }, default: <value> } }`.

Timestamp format selection (MANDATORY):
- Inspect every timestamp/date column in the input sample. If a column is already strict ISO 8601 (e.g. `"2025-01-12T06:04:00Z"` or `"2025-01-12T06:04:00.000Z"`) use `transform: iso_millis`.
- If it is anything else — `"3/12/2016 2:00:00 AM"`, `"2016-03-12 02:00"`, `"12-Mar-2016"`, epoch seconds, etc. — emit `parse_timestamp` with the exact `strptime` directives that match the observed sample. Do NOT guess; pick directives that round-trip every example value in the sample.
- Common directives: `%Y` 4-digit year, `%m` zero-padded month, `%d` zero-padded day, `%H` 24-hour, `%I` 12-hour, `%M` minutes, `%S` seconds, `%p` AM/PM, `%z` ±HHMM offset. The Fitabase export uses `%m/%d/%Y %I:%M:%S %p`.
- If date and time arrive in two columns, combine them with a `template:` spec and apply `parse_timestamp:` to the combined string.

Rule structure:
- id, description (free text).
- type: one of "measurement" | "observation" | "survey" | "event" | "summary" | "session".
- category: a string (often a value-spec resolving the category from `@item`).
- granularity: "instant" | "interval" | "daily" | "session" | "unknown".
- iterate: path to a list inside the record — one event per element. `@item` references resolve against that element.
- iterate_object: expand an object's keys into one event per key.
    - `source` (optional): path to the source dict. Defaults to the root record. Use `"."` or omit for flat CSVs.
    - `entries: [{ key, label }, ...]` — explicit list of keys to iterate.
    - `all_keys: true` — auto-iterate every key in the source dict. Use `exclude: [Timestamp, ...]` to skip non-question columns. Preferred for questionnaire/survey CSVs with many columns — avoids listing every column.
    - Each iteration produces an item with fields: `key`, `name` (= key), `label`, `value`. Reference them as `@item.name`, `@item.value`, `@item.label`, etc.
- timestamp: { start: <spec>, end?: <spec>, duration_seconds?: <spec> }.
- payload: { value, raw_value, unit, label, components: [{name, value, unit?}, ...] }.
- Value vs. components separation (MANDATORY):
    - `payload.value` holds a SINGLE scalar measurement (e.g., heart rate = 72).
    - `payload.components[]` holds MULTIPLE distinct sub-measurements of a composite concept (e.g., blood pressure systolic + diastolic, or heart-rate zone with min/max/minutes/calories).
    - NEVER duplicate the same data in both places. If the concept has one numeric value, use `payload.value` and omit components. If the concept is composite, use components only and set `payload.value` to null (or to a meaningful aggregate like "total minutes" when one exists).
    - Anti-pattern: do NOT create a component whose value path equals `payload.value`'s path — this produces duplicate data in the canonical event and in the FHIR Observation (value[x] + component[] with the same value).
- extensions: free-form `{ key: <spec> }` map; keys prefixed with the source name (e.g. "withings.attrib").
- parent: another rule's `id` — produced events are linked via `parent_event_id`.
- quality: { flags: [...] }. Each flag is either an unconditional `{ code, severity, stage, message }` or a conditional `{ condition: { path, equals }, code, severity, stage, message }`.

If the source has no per-record timestamp at all, declare a literal ISO-8601 string at `timestamp.start` and add an unconditional `SYNTHETIC_TIMESTAMP` quality flag.

Cleaner block (`clean`):
- `heuristics`: ordered list, each entry either a name string or `{ name, ...params }`. Closed enum:
    - `whitespace` — strip leading/trailing whitespace on string fields. No params.
    - `timestamp_normalizer` — normalize timestamps to ISO 8601 UTC. Params: `accept_formats: ["%m/%d/%Y %I:%M:%S %p", ...]` (strptime format strings tried in order after the built-in ISO/date-only handling).
    - `type_coercer` — coerce numeric strings on payload.value and components. No params.
    - `unit_inferrer` — fill `payload.unit` when the adapter left it null. Params: `mappings: { "<source>|<category>": "<unit>", ... }`.
- Listing only a subset of names (or omitting some) means the others are skipped. Order in the list is the order of execution.
- Default chain when `clean` is omitted: whitespace → timestamp_normalizer → type_coercer → unit_inferrer (each with defaults).

Validator block (`validate`):
- `enabled`: subset of `[required_fields, timestamp_window, payload_shape, unit_whitelist, range]`. Canonical order is preserved regardless of the order you list. Omit `enabled` to run all five.
- `timestamp_window: { min, max }` — overrides the global `timestamp_window`. Accepts ISO strings or `now+Xd`/`now-Xh`.
- `categories.<canonical_category>:` per-category overlay on top of the global quality_rules.yaml. Each per-category key is a SHALLOW REPLACE — providing `range` replaces the global range wholesale; providing `unit_whitelist` replaces that list wholesale; same for `expected_fields`.
    - `expected_fields: [<dotted-paths>]` — fields the qualifier's completeness check will look for.
    - `unit_whitelist: [<unit-strings>]` — values `payload.unit` may take. Otherwise emits `UNIT_NOT_IN_WHITELIST` (warning).
    - `range: { min, max, on_violation: { severity, code } }` — numeric range on `payload.value`. `severity ∈ {info, warning, error}`. `code` is the QualityFlag.code emitted on violation.

Qualifier block (`qualify`):
- `enabled`: subset of `[completeness, duplicates, outliers, conformance, plausibility]`. Omit to run all five.
- `outliers: { hampel_k: 3.5, min_group_size: 5 }` — Hampel test (median ± k·MAD) per `(subject_id, category)`. Lowering k flags more events; raising it flags fewer. Lowering `min_group_size` makes the test more aggressive on sparse data — only do this with statistical justification, since MAD collapses to 0 on tiny groups.
- `duplicates: { fields: [subject_id, category, timestamp, payload.value], value_round_digits: 3 }` — the fingerprint over which to detect duplicates. `fields` accepts any dotted path on the canonical event.
- `plausibility: { warning_count_for_review: 1 }` — number of WARNING flags after which `quality.plausibility` becomes `"review"`. Any ERROR forces `"exclude"` regardless.
- `completeness: { expected_fields: { <category>: [<paths>] } }` — overrides per-category expected_fields when computing the completeness ratio.

FHIR block (`fhir`):
- `enabled: true | false` — when false, the pipeline returns no bundle. Default: true.
- `bundle_type: transaction | collection` — `transaction` adds `entry.request.method/url` and is suitable for POST-ing to a FHIR server. `collection` omits the request slice. Default: `transaction`.
- `include`: subset of `[Patient, Observation, Device, Provenance, Questionnaire]`. Default: `[Patient, Observation, Questionnaire]`. Add `Device` when `context.device` is meaningful in the sample, and `Provenance` when the user explicitly wants an audit trail attached to the bundle. `Questionnaire` emits one definition resource per unique survey category — each `QuestionnaireResponse` links back to it.
- Hardcoded behaviors (NOT user-configurable here):
    - Every CodeableConcept is text-only. Codesystem binding (LOINC / SNOMED / UCUM) is the future MAPPED stage's responsibility, not this stage's.
    - `event.type=measurement|observation|event|session|summary` → `Observation`. `event.type=survey` → `QuestionnaireResponse`.
    - `quality.plausibility="exclude" → status="entered-in-error"`, `"review" → "amended"`, otherwise `"final"`.
    - `payload.value` is mapped to `valueQuantity` (numeric) / `valueBoolean` / `valueString`. `payload.components[]` becomes `Observation.component[]` or `QuestionnaireResponse.item[]`.
    - Subject + Device + Observation references are stable UUID5 derivations of `subject_id`, `(source, device)`, and `event_id` respectively — re-running the pipeline produces identical bundle URIs.

OMOP CDM block (`omop`):
- `enabled: true | false` — when false, the pipeline returns no OMOP CDM tables. Default: true.
- `include`: subset of `[person, measurement, observation, device_exposure, observation_period]`. Default: all five tables.
    - `person` — one row per unique `subject_id`. Demographics are unknown for wearable data (concept_id=0).
    - `measurement` — numeric health data (heart rate, weight, blood pressure, steps, SpO2, etc.). Routed by domain from the OMOPHub FHIR Resolver.
    - `observation` — categorical/behavioural data (surveys, game scores, session metadata). Fallback for events whose domain is not Measurement.
    - `device_exposure` — one row per unique (subject, device) pair.
    - `observation_period` — one row per subject spanning the earliest-to-latest timestamp of emitted rows.
- Hardcoded behaviors (NOT user-configurable here):
    - Table routing is domain-driven: the pipeline batch-resolves FHIR codings via the OMOPHub FHIR Resolver API (`POST /v1/fhir/resolve/batch`). The response's `target_table` determines which CDM table each event goes to. A FHIR Observation with a LOINC lab code routes to `measurement`, not `observation`.
    - Both `*_concept_id` (OMOP standard concept via "Maps to") and `*_source_concept_id` (original vocabulary concept) are populated.
    - `*_type_concept_id` is derived from `context.modality`: wearable/sensor/app/game/vr → 32865 (Patient self-report), scale → 705183 (Patient self-tested), survey → 32862 (Patient filled survey), unknown → 32817 (EHR).
    - Events with `quality.plausibility="exclude"` are skipped entirely.
    - Unmapped events (concept_id=0) are still emitted — OMOP convention — and tracked in a separate `unmapped` audit list.
    - `payload.components[]` (e.g. blood pressure systolic/diastolic) become separate rows in the target table.
- Always include the `omop:` block when you include a `fhir:` block.

Defaults & omission rule:
- Every block, every nested key, every parameter is optional. Omitted = current default behavior.
- If you cannot infer a parameter from the input sample, OMIT it. Do not invent thresholds. The defaults are statistically defensible and match the existing pipeline behavior.
- Only emit a per-category override under `validate.categories` when the source genuinely needs to deviate from the global `quality_rules.yaml` (e.g. a new unit or a different range). Otherwise leave the global rule in charge.

Return ONE YAML document — no markdown fencing, no preamble, no trailing commentary. Only the YAML.
"""


def _load_few_shot() -> str:
    blocks: list[str] = []
    for name in FEW_SHOT_FILES:
        p = CONFIG_EXAMPLES_DIR / name
        if p.is_file():
            blocks.append(f"### Example: {name}\n\n```yaml\n{p.read_text(encoding='utf-8').strip()}\n```")
    return "\n\n".join(blocks)


def _load_canonical_model() -> str:
    if CANONICAL_MODEL_PATH.is_file():
        return CANONICAL_MODEL_PATH.read_text(encoding="utf-8")
    return ""


def build_system_prompt() -> str:
    return (
        "You generate YAML adapter configs for the Progressive Harmonization ETL. "
        "The config drives a generic engine that turns source records into Canonical Events.\n\n"
        "## Canonical Event model (Python dataclasses — target shape of every emitted event)\n\n"
        "```python\n" + _load_canonical_model() + "\n```\n\n"
        "## " + DSL_OVERVIEW + "\n\n"
        "## Reference configs\n\n"
        + _load_few_shot()
    )


def _truncate_sample(data: Any) -> str:
    """Serialize `data` to JSON but cap it at MAX_SAMPLE_BYTES.

    Strategy: if top-level is a list, keep up to the first 3 elements; if still
    too large, truncate the string and mark it.
    """
    if isinstance(data, list):
        sample = data[: min(3, len(data))]
        note = f"(showing {len(sample)} of {len(data)} top-level elements)"
        body = json.dumps(sample, indent=2, default=str)
    else:
        note = ""
        body = json.dumps(data, indent=2, default=str)

    if len(body.encode("utf-8")) > MAX_SAMPLE_BYTES:
        body = body.encode("utf-8")[:MAX_SAMPLE_BYTES].decode("utf-8", errors="ignore")
        body += "\n... [truncated]"
    return (note + "\n" + body) if note else body


def build_user_prompt(
    *,
    description: str,
    hints: str | None,
    data: Any,
    source: str | None,
) -> str:
    parts = [
        "## Data description (user-supplied)",
        description.strip() or "(no description provided)",
    ]
    if hints:
        parts += ["", "## Extra hints", hints.strip()]
    if source:
        parts += ["", f"## `match.source` must equal", f"`{source}`"]
    parts += [
        "",
        "## Input data sample",
        "```json",
        _truncate_sample(data),
        "```",
        "",
        "Before emitting: derive a rigid `match.record` from the sample above. "
        "Require existence of every field your `defaults` and `emit` rules read, "
        "require `type: array, non_empty: true` on every `iterate` target, and "
        "pin any discriminator field with `equals` or `in`. Produce the YAML "
        "config now. Output only YAML.",
    ]
    return "\n".join(parts)


def build_fix_system_prompt() -> str:
    """System prompt for the /api/suggest-config-fix LLM call.

    Same DSL + canonical model + few-shot examples as generation, but with an
    additional instruction: the LLM is patching an existing YAML that emitted
    0 events, given the diagnostics report and one sample record.
    """
    return (
        "You repair YAML adapter configs for the Progressive Harmonization ETL. "
        "The user ran a config that emitted zero events (or skipped rules). "
        "You will be given the failing YAML, a diagnostics report explaining "
        "which match clauses or emit rules failed, and one sample input record. "
        "Return a corrected YAML config — the same shape as the original, with "
        "only the necessary changes to make the failing rules emit events.\n\n"
        "## Canonical Event model (Python dataclasses — target shape of every emitted event)\n\n"
        "```python\n" + _load_canonical_model() + "\n```\n\n"
        "## " + DSL_OVERVIEW + "\n\n"
        "## Reference configs\n\n"
        + _load_few_shot()
    )


def build_fix_user_prompt(
    *,
    yaml_text: str,
    diagnostics: dict[str, Any],
    sample_record: Any,
    description: str,
) -> str:
    parts = [
        "## Data description (user-supplied)",
        description.strip() or "(no description provided)",
        "",
        "## Failing YAML config",
        "```yaml",
        yaml_text.strip(),
        "```",
        "",
        "## Diagnostics report (what went wrong)",
        "```json",
        json.dumps(diagnostics, indent=2, default=str),
        "```",
        "",
        "## One sample input record (the failing config was run against records like this)",
        "```json",
        _truncate_sample(sample_record),
        "```",
        "",
        "Identify the failing match clauses and emit-rule paths from the diagnostics, "
        "trace them against the sample record, and return a single corrected YAML "
        "config. Do not invent fields the sample record doesn't contain — use the "
        "paths that actually exist. Output only YAML, no prose, no fencing.",
    ]
    return "\n".join(parts)


def build_concept_suggest_system_prompt() -> str:
    return (
        "You are a clinical terminology specialist. Your task is to map health-data "
        "concept slots to standard FHIR coding systems.\n\n"
        "You have a `search_terminology` tool. Use it to find the best code for each slot:\n"
        "- For **code** and **component** slots: search `loinc` and `snomed` first..\n"
        "- For **unit** slots: search `ucum`.\n"
        "- Skip **category** slots — they already have defaults.\n\n"
        "CRITICAL RULE: You MUST NEVER invent, guess, or recall codes from memory. "
        "Every code you return MUST be copied verbatim (system, code, and display) from "
        "a `search_terminology` tool result. Do NOT fabricate codes.\n\n"
        "Search tips:\n"
        "- You can search by code number to validate a code you know, e.g. search "
        'for "8867-4" to confirm the LOINC code for heart rate.\n'
        "- If a text search returns poor results, try searching by the specific code "
        "number instead.\n"
        "- Use the slot's `category` field to judge relevance. For wearable/vital-signs "
        "data, reject neonatal codes (Apgar, Ballard) and procedure codes.\n"
        "- When multiple results match, prefer the one whose display name most closely "
        "matches the slot label.\n\n"
        "Strategy:\n"
        "1. Read the slot list, noting each slot's category for context.\n"
        "2. Call `search_terminology` for each slot. Try multiple search queries if the "
        "first returns poor results (synonyms, code numbers, broader/narrower terms).\n"
        "3. From the tool results, ALWAYS pick the single best match per slot — even if "
        "the match is imperfect. Copy the `system`, `code`, and `display` fields exactly "
        "as returned by the tool. Use the confidence level to indicate match quality.\n"
        "4. Only put a slot in `no_matches` if the tool returned ZERO results across all "
        "your search attempts for that slot.\n"
        "5. For each suggestion, assess confidence:\n"
        "   - **high**: the returned code's display closely matches the slot label AND "
        "the code is semantically correct for the measured concept.\n"
        "   - **medium**: the best available code is related but not an exact match "
        "(e.g. a broader concept, or a partial overlap in meaning).\n"
        "   - **low**: the best available code is a stretch — the user should review "
        "and likely replace it.\n\n"
        "Respond with ONLY a JSON object with two top-level keys:\n"
        '  "suggestions": maps slot keys to codings with confidence:\n'
        '    {"<key>": {"system": "<uri>", "code": "<code>", "display": "<name>", '
        '"confidence": "high"|"medium"|"low"}, ...}\n'
        '  "no_matches": maps slot keys where no standard code exists to a reason:\n'
        '    {"<key>": {"reason": "<why no code exists>"}, ...}\n\n'
        "Every non-category slot MUST appear in exactly one of `suggestions` or `no_matches`.\n"
        "Output only the JSON object — no markdown fencing, no prose."
    )


def _extract_category(slot: dict[str, Any]) -> str:
    """Extract the category segment from a slot key like 'code|heart-rate|Heart Rate'."""
    key = slot.get("key", "")
    parts = key.split("|")
    if len(parts) >= 2:
        return parts[1]
    return ""


def build_concept_suggest_user_prompt(slots: list[dict[str, Any]]) -> str:
    lines = ["Map the following concept slots to standard terminology codes. "
             "Try synonyms, abbreviations, and code numbers where helpful."
             "Always try the 'label' as search query first.\n"]
    for i, s in enumerate(slots, 1):
        category = _extract_category(s)
        sample_parts = []
        if s.get("sample"):
            sv = s["sample"]
            if sv.get("value") is not None:
                sample_parts.append(f"value={sv['value']}")
            if sv.get("unit"):
                sample_parts.append(f"unit={sv['unit']}")
        sample_str = f", sample: {{{', '.join(sample_parts)}}}" if sample_parts else ""
        cat_str = f', category="{category}"' if category else ""
        lines.append(
            f'{i}. key="{s["key"]}", kind={s["kind"]}, label="{s["label"]}"'
            f'{cat_str}, count={s["count"]}{sample_str}'
        )
    return "\n".join(lines)


def strip_code_fence(text: str) -> str:
    """Strip a leading ```yaml / ```yml / ``` fence and trailing ``` if present."""
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t.strip() + "\n"

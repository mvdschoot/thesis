from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIGS_DIR = BACKEND_DIR / "configs"
CANONICAL_MODEL_PATH = BACKEND_DIR / "src" / "models" / "canonical.py"

FEW_SHOT_FILES = ["withings-body-scale.yaml", "app-usage-daily.yaml"]

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

Match-block rigidity (MANDATORY):
- Do NOT rely on `match.source` alone — that lets the engine try to transform records you can't actually handle. For every config you generate, the `record` list MUST:
  1. Assert `exists: true` on every field the `defaults` block reads (subject_id source path, source_record_id template fields, timestamps).
  2. Assert `type: "array", non_empty: true` on every path used as an `iterate` target in the `emit` rules.
  3. Assert `type: "object"` on every intermediate container your emit paths walk through before reaching a leaf.
  4. Pin any discriminator field (e.g. `dataType`, `measurementType`, `recordKind`) with `equals` or `in` to the exact value(s) this config is designed for. If the same source emits multiple record kinds, use `in: [...]` enumerating only the kinds this config handles.
- A match block that would accept a garbage record is a bug. Prefer overly strict criteria; false positives produce unusable events, false negatives are surfaced as "no config matches" in the UI so the user can widen them.

Value-spec forms (use anywhere a value is needed):
- literal: `"foo"`, `42`, `null`
- path: `{ path: "some.nested.key" }` — dot notation, supports `[0]` indexing. Prefix `@item.` inside an iterated rule to reference the current iteration element.
- transform: `{ path: "...", transform: "start_of_day" | "end_of_day" | "iso_date" | "iso_millis" | "to_int" | "to_float" }`
- fallback: `{ path: "...", fallback: <another-spec> }` — the fallback is itself a full value-spec (recursive).
- template: `{ template: "literal {path.to.field} more {@item.foo}" }` — brace-interpolation.
- composite timestamp: `{ date_from: <spec>, time_from: <spec> }` → produces `YYYY-MM-DDTHH:MM:SS.sssZ`.
- arithmetic: `{ multiply: [<spec>, <spec>, ...] }`.
- lookup table: `{ lookup: { key: <spec>, map: { "k1": "v1", ... }, default: <value> } }`.

Rule structure:
- id, description (free text).
- type: one of "measurement" | "observation" | "survey" | "event" | "summary" | "session".
- category: a string (often a value-spec resolving the category from `@item`).
- granularity: "instant" | "interval" | "daily" | "session" | "unknown".
- iterate: path to a list inside the record — one event per element. `@item` references resolve against that element.
- iterate_object: `{ source, entries: [{ key, label }, ...] }` — expand an object with fixed keys.
- timestamp: { start: <spec>, end?: <spec>, duration_seconds?: <spec> }.
- payload: { value, raw_value, unit, label, components: [{name, value, unit?}, ...] }.
- extensions: free-form `{ key: <spec> }` map; keys prefixed with the source name (e.g. "withings.attrib").
- parent: another rule's `id` — produced events are linked via `parent_event_id`.
- quality: { flags: [...] }. Each flag is either an unconditional `{ code, severity, stage, message }` or a conditional `{ condition: { path, equals }, code, severity, stage, message }`.

If the source has no per-record timestamp at all, declare a literal ISO-8601 string at `timestamp.start` and add an unconditional `SYNTHETIC_TIMESTAMP` quality flag.

Return ONE YAML document — no markdown fencing, no preamble, no trailing commentary. Only the YAML.
"""


def _load_few_shot() -> str:
    blocks: list[str] = []
    for name in FEW_SHOT_FILES:
        p = CONFIGS_DIR / name
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

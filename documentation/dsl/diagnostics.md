# Diagnostics — debugging a config

Every `/api/transform` response includes an `adapter_diagnostics` object that reports, per rule,
how many events were emitted and *why* a rule produced none. This is your first stop when a config
emits fewer events than expected.

## The mental checklist

```
0 events overall?         -> the match block probably rejected the record
some rules emit nothing?  -> check that rule's `when:`, `iterate:`, or `parent:`
fewer events than rows?   -> a `when:` gate or an empty/missing iterate path
```

## Skip codes

When a rule fires 0 events, the diagnostics record a skip code:

| Code | Trigger | Fix |
|---|---|---|
| `predicate_mismatch` | a `match.record` clause failed — the record was not routed to this config at all | loosen the match block; verify the sample actually has those top-level fields |
| `when_not_met` | the rule's `when:` predicate did not match this record | confirm the discriminator field/value; this is expected for rules gated to other kinds |
| `parent_rule_empty` | the `parent:` rule produced no events for the record | fix the parent rule first |
| `iterate_path_none` | the `iterate:` path did not resolve | check the dot-path against the sample |
| `iterate_not_list` | the `iterate:` path resolved to a non-array | point it at the actual array |
| `iterate_empty` | the `iterate:` array was empty | nothing to emit — usually fine |
| `iterate_object_source_none` | the `iterate_object.source` path did not resolve | check the source path (use `.` for the root record) |
| `iterate_object_source_not_dict` | the source resolved to a non-object | point `source` at an object |
| `iterate_object_source_invalid` | the `source` spec is malformed | use a string path, `{ path: ... }`, or omit it |
| `iterate_object_keys_missing` | none of the `entries` keys exist, or `all_keys` produced nothing, or neither `entries` nor `all_keys: true` was set | fix the keys or switch to `all_keys: true` |
| `redundant_component_dropped` | a component's `value` spec equalled `payload.value` and was stripped | remove that component — a value must not also be a component |

## Most common causes

1. **Over-strict `match` block.** The number-one failure: the match block matches on a nested
   path or enumerates fields that aren't always present, so it rejects the very data it was built
   for. Keep it to 2–3 top-level `exists`/`equals` checks. See
   [Reference → match](reference.md#match-required).
2. **Wrong `source`.** `match.source` must equal the request's `source` exactly.
3. **Wrong timestamp format.** A `parse_timestamp` whose directives don't match the sample returns
   the value unchanged and the validator later flags it — but the event is still emitted. If you
   see events with empty timestamps, recheck the format string.
4. **`@item` outside an iterated rule.** `@item` only resolves inside `iterate:` /
   `iterate_object:` rules; elsewhere it yields the spec's `fallback` (or null).

## Using the LLM repair endpoint

If you generated the config with the LLM, `POST /api/suggest-config-fix` takes the failing YAML,
the diagnostics report, and one sample record, and returns a corrected config. The web UI exposes
this as a one-click "fix" when a transform emits zero events.

# Value specs

A **value spec** is the mini-language used anywhere a config needs a value — `payload.value`,
`timestamp.start`, `category`, `subject_id`, `extensions`, component values, and more. A value
spec resolves against the current input record (and, inside an iterated rule, the current element).

A spec is either a **literal** or a **dict** with one of the forms below.

## Literals

Any plain scalar is used verbatim:

```yaml
unit: "bpm"          # string
value: 42            # number
flag: true           # boolean
device: null         # null
```

## Paths

`{ path: "..." }` reads a value by dot-notation, with `[index]` array access.

```yaml
{ path: "userId" }
{ path: "measurementValue.activities-heart[0].value" }
```

### Special path prefixes

| Prefix | Resolves to | Use |
|---|---|---|
| `@record_index` | the 0-based row/record number | a stable `subject_id` when there is no person id |
| `@event` / `@event.x` | the whole record / a field on it | inside an iterated rule, reach back up to record-level fields |
| `@item` / `@item.x` | the current iteration element / a field on it | inside `iterate:` / `iterate_object:` rules |

```yaml
# Inside a rule that iterates an array of recipes:
payload:
  value: { path: "@item.recipeId" }   # per-element field
extensions:
  date: { path: "@event.date" }       # event-level field
```

!!! note
    Plain unprefixed paths also resolve against the record inside an iterated rule, but prefer
    `@event.` to make the intent explicit.

## Transforms

`{ path: "...", transform: "<name>" }` post-processes the resolved value.

| Transform | Effect | Example |
|---|---|---|
| `start_of_day` | take the date part, set to `00:00:00.000Z` | `2025-01-12T06:04:00Z` → `2025-01-12T00:00:00.000Z` |
| `end_of_day` | date part at `23:59:59.999Z` | → `2025-01-12T23:59:59.999Z` |
| `iso_date` | date part at `00:00:00.000Z` | `2025-01-12` → `2025-01-12T00:00:00.000Z` |
| `iso_millis` | normalize an already-ISO timestamp to millisecond precision | `2025-01-12T06:04:00Z` → `2025-01-12T06:04:00.000Z` |
| `to_int` | coerce to int (null on failure) | `"42"` → `42` |
| `to_float` | coerce to float (null on failure) | `"3.14"` → `3.14` |

## Fallback

`{ path: "...", fallback: <spec> }` — if the primary path is null, resolve the fallback (which is
itself a full value spec, so fallbacks can chain).

```yaml
value:
  path: "preferredValue"
  fallback:
    path: "legacyValue"
    fallback: { path: "rawValue" }
```

## Template

`{ template: "..." }` — brace-interpolation. Each `{...}` is a path (or `@item.x`, `@event.x`,
`@record_index`). Missing/null slots render as empty string.

```yaml
source_record_id:
  template: "withings:{userId}:{measurementType.typeValue}:{measurementDateTime}"
```

A template can be combined with `parse_timestamp:` to merge separate date and time columns into
one parsed timestamp (see below).

## Timestamps

Choosing the right timestamp spec is mandatory for usable events. Inspect every date/time column
in your sample and pick:

=== "Already strict ISO 8601"

    Use `iso_millis` to normalize precision.

    ```yaml
    timestamp:
      start: { path: "measurementDateTime", transform: "iso_millis" }
    ```

=== "Any other single format"

    Use `parse_timestamp` with exact `strptime` directives. Emits ISO 8601 in UTC (naive values
    assumed UTC; aware values converted).

    ```yaml
    timestamp:
      start: { path: "createdAt", parse_timestamp: "%m/%d/%Y %I:%M:%S %p" }
    ```

=== "Date and time in two columns"

    Either combine via `template:` + `parse_timestamp:`, or use the composite form:

    ```yaml
    # composite form -> "YYYY-MM-DDTHH:MM:SSZ"
    timestamp:
      start:
        date_from: { path: "ActivityDate" }
        time_from: { path: "ActivityTime" }
    ```

    ```yaml
    # template form
    timestamp:
      start:
        template: "{ActivityDate} {ActivityTime}"
        parse_timestamp: "%m/%d/%Y %I:%M:%S %p"
    ```

Common `strptime` directives: `%Y` 4-digit year, `%m` zero-padded month, `%d` day, `%H` 24-hour,
`%I` 12-hour, `%M` minutes, `%S` seconds, `%p` AM/PM, `%z` ±HHMM offset. Pick directives that
round-trip **every** example value in your sample — do not guess.

!!! tip "No timestamp at all?"
    Set a literal ISO string at `timestamp.start` and add an unconditional `SYNTHETIC_TIMESTAMP`
    flag (see [Quality & flags](quality-and-flags.md)).

## Arithmetic

`{ multiply: [<spec>, <spec>, ...] }` — product of the operands. Any null operand makes the whole
result null.

```yaml
value:
  multiply:
    - { path: "perUnit" }
    - { path: "quantity" }
```

## Lookup table

`{ lookup: { key: <spec>, map: { ... }, default: <value> } }` — resolve the key spec, then map it.

```yaml
category:
  lookup:
    key: { path: "measurementType.typeDescription" }
    map:
      "Weight": "weight"
      "Height": "height"
      "Heart Rate": "heart-rate"
    default: "unknown"
```

Lookups are how one rule handles many metric kinds: derive both `category` and `unit` from the
same source field.

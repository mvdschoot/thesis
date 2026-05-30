"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { searchTerminology, suggestConcepts, type NoMatchSlot, type TerminologySystem } from "@/lib/api";
import { cx } from "@/lib/cx";
import type { Coding, ConceptSlot, ConceptSlotKind } from "@/lib/types";

interface Props {
  slots: ConceptSlot[];
  mappings: Record<string, Coding>;
  noMatches: Record<string, NoMatchSlot>;
  onChange: (key: string, coding: Coding | null) => void;
  onBulkChange: (mappings: Record<string, Coding>) => void;
  onNoMatchesChange: (noMatches: Record<string, NoMatchSlot>) => void;
  onRerun: () => void;
  running: boolean;
}

const KIND_LABEL: Record<ConceptSlotKind, string> = {
  code: "Observation code & component (LOINC / SNOMED CT)",
  unit: "valueQuantity unit (UCUM)",
  category: "Observation.category (FHIR)",
};

const KIND_BLURB: Record<ConceptSlotKind, string> = {
  code: "Headline measurement and component codings. Toggle LOINC ↔ SNOMED CT inside the search box. Bind once per concept — the same concept used as a value and as a component is bound a single time.",
  unit: "UCUM code/system on numeric valueQuantity. Bind once per unit text.",
  category: "Observation category bucket. Defaults are pre-bound; override only if needed.",
};

// Standard observation-category value set — used by the category picklist.
const CATEGORY_OPTIONS: Coding[] = [
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "vital-signs", display: "Vital Signs" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "activity", display: "Activity" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "exam", display: "Exam" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "survey", display: "Survey" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "social-history", display: "Social History" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "imaging", display: "Imaging" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "laboratory", display: "Laboratory" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "procedure", display: "Procedure" },
  { system: "http://terminology.hl7.org/CodeSystem/observation-category", code: "therapy", display: "Therapy" },
];

function defaultSystemForSlot(slot: ConceptSlot): TerminologySystem | null {
  if (slot.kind === "unit") return "ucum";
  if (slot.kind === "code") return "loinc";
  return null;
}

// Which vocabularies a slot's search box can switch between.
function vocabOptionsForSlot(slot: ConceptSlot): TerminologySystem[] {
  if (slot.kind === "unit") return ["ucum"];
  if (slot.kind === "code")
    return ["loinc", "snomed", "rxnorm", "icd10", "cpt"];
  return [];
}

const SYSTEM_LABEL: Record<TerminologySystem, string> = {
  loinc: "LOINC",
  ucum: "UCUM",
  snomed: "SNOMED CT",
  rxnorm: "RxNorm",
  icd10: "ICD-10",
  cpt: "CPT-4",
};

function formatSample(slot: ConceptSlot): string {
  const v = slot.sample.value;
  const u = slot.sample.unit;
  const ts = slot.sample.timestamp;
  const parts: string[] = [];
  if (v !== undefined && v !== null) parts.push(String(v));
  if (u) parts.push(u);
  const head = parts.join(" ");
  if (ts) return head ? `${head} @ ${ts}` : `@ ${ts}`;
  return head || "—";
}

export default function ConceptsPanel({
  slots,
  mappings,
  noMatches,
  onChange,
  onBulkChange,
  onNoMatchesChange,
  onRerun,
  running,
}: Props) {
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const grouped = useMemo(() => {
    const g: Record<ConceptSlotKind, ConceptSlot[]> = {
      code: [],
      unit: [],
      category: [],
    };
    for (const s of slots) g[s.kind].push(s);
    return g;
  }, [slots]);

  const unboundCount = useMemo(
    () =>
      slots.filter(
        (s) =>
          (s.kind === "code" || s.kind === "unit") &&
          !mappings[s.key],
      ).length,
    [slots, mappings],
  );

  async function handleSuggest() {
    const unbound = slots.filter(
      (s) => s.kind !== "category" && !mappings[s.key],
    );
    if (unbound.length === 0) return;
    setSuggesting(true);
    setSuggestError(null);
    try {
      const res = await suggestConcepts(unbound);
      if (Object.keys(res.suggestions).length > 0) {
        onBulkChange(res.suggestions);
      }
      if (Object.keys(res.no_matches).length > 0) {
        onNoMatchesChange(res.no_matches);
      }
      if (res.errors.length > 0) {
        setSuggestError(res.errors.join("; "));
      }
    } catch (e: unknown) {
      setSuggestError(e instanceof Error ? e.message : "Suggestion failed.");
    } finally {
      setSuggesting(false);
    }
  }

  if (slots.length === 0) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-body">
          <p className="muted">
            No concept slots detected. Run the pipeline first — slots are derived from
            the events in the most recent transform.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <span className="eyebrow">
          MAPPED · {slots.length} slot{slots.length === 1 ? "" : "s"} ·{" "}
          {unboundCount === 0 ? (
            <span className="chip ok">all code/unit slots bound</span>
          ) : (
            <span className="chip warn">{unboundCount} unbound</span>
          )}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            className="btn"
            onClick={handleSuggest}
            disabled={suggesting || running || unboundCount === 0}
            title="Use AI to suggest terminology codes for all unbound slots"
          >
            {suggesting ? "Suggesting…" : "Suggest with AI"}
          </button>
          <button
            className="btn primary"
            onClick={onRerun}
            disabled={running}
            title="Re-run /api/transform with the current concept picks"
          >
            {running ? "Re-running…" : "Re-transform with concepts"}
          </button>
        </div>
      </div>
      <div className="card-body">
        <p className="muted" style={{ marginTop: 0, maxWidth: 720 }}>
          Pick one concept per slot — all events sharing a slot get the same{" "}
          <span className="mono">coding[]</span> in the FHIR bundle. Wearable data is
          repetitive, so a single LOINC code covers most events. Free-search slots
          use OMOPHub semantic search (LOINC / UCUM / SNOMED CT); category uses the fixed FHIR value set.
        </p>
        {suggestError && (
          <div
            className="qflag warn"
            style={{ marginBottom: 12 }}
          >
            <div className="qf-bar" />
            <div>
              <div className="qf-code">AI_SUGGEST</div>
              <div className="qf-msg">{suggestError}</div>
            </div>
          </div>
        )}
        {(["code", "unit", "category"] as ConceptSlotKind[]).map((kind) => {
          const rows = grouped[kind];
          if (rows.length === 0) return null;
          return (
            <section key={kind} style={{ marginTop: 18 }}>
              <h3 style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 600 }}>
                {KIND_LABEL[kind]}{" "}
                <span className="muted" style={{ fontWeight: 400 }}>
                  · {rows.length}
                </span>
              </h3>
              <p className="muted" style={{ margin: "0 0 8px", fontSize: 12 }}>
                {KIND_BLURB[kind]}
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {rows.map((slot) => (
                  <SlotRow
                    key={slot.key}
                    slot={slot}
                    coding={mappings[slot.key] ?? null}
                    noMatch={noMatches[slot.key] ?? null}
                    onChange={(c) => onChange(slot.key, c)}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

interface SlotRowProps {
  slot: ConceptSlot;
  coding: Coding | null;
  noMatch: NoMatchSlot | null;
  onChange: (coding: Coding | null) => void;
}

function SlotRow({ slot, coding, noMatch, onChange }: SlotRowProps) {
  const [open, setOpen] = useState(false);
  const effective = coding ?? slot.default_coding ?? null;

  return (
    <div
      style={{
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: 12,
        background: "var(--bg-1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0, flex: "1 1 220px" }}>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{slot.label}</div>
          <div className="muted mono" style={{ fontSize: 11 }}>
            {slot.count} event{slot.count === 1 ? "" : "s"} · sample: {formatSample(slot)}
          </div>
        </div>
        <div style={{ flex: "1 1 260px", minWidth: 0 }}>
          {effective ? (
            <CodingChip coding={effective} pinned={!!coding} />
          ) : noMatch ? (
            <span className="chip info" title={noMatch.reason}>no standard code</span>
          ) : (
            <span className="chip warn">unbound</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {slot.kind === "category" ? (
            <CategorySelect
              value={coding ?? slot.default_coding ?? null}
              onChange={onChange}
            />
          ) : (
            <>
              {!effective && (
                <button
                  className="btn tiny"
                  onClick={() => {
                    const slug = slot.label
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "-")
                      .replace(/^-|-$/g, "");
                    onChange({
                      system: "urn:harmonization:local",
                      code: slug,
                      display: slot.label,
                    });
                  }}
                  title={`Create local coding: urn:harmonization:local|${slot.label}`}
                >
                  Use local coding
                </button>
              )}
              <button
                className={cx("btn tiny", open && "primary")}
                onClick={() => setOpen((v) => !v)}
              >
                {open ? "Close" : coding ? "Change" : "Search"}
              </button>
              {coding && (
                <button
                  className="btn tiny ghost"
                  onClick={() => onChange(null)}
                  title="Clear this slot"
                >
                  Clear
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {open && slot.kind !== "category" && (
        <div style={{ marginTop: 10 }}>
          <SearchBox
            initialSystem={defaultSystemForSlot(slot)!}
            vocabularies={vocabOptionsForSlot(slot)}
            initialQuery={slot.label}
            onPick={(c) => {
              onChange(c);
              setOpen(false);
            }}
          />
        </div>
      )}
    </div>
  );
}

// OMOP standard_concept indicator. `undefined` (e.g. local/category codings,
// not sourced from OMOPHub) renders nothing; "S" is standard, "C"/null are not.
function StandardBadge({ value }: { value?: "S" | "C" | null }) {
  if (value === undefined) return null;
  if (value === "S") {
    return (
      <span className="chip ok" title="OMOP standard concept (standard_concept = S)">
        Standard
      </span>
    );
  }
  const title =
    value === "C"
      ? "OMOP classification concept (standard_concept = C) — not a standard concept"
      : "Non-standard concept (standard_concept is null)";
  return (
    <span className="chip" title={title}>
      Non-standard
    </span>
  );
}

function CodingChip({ coding, pinned }: { coding: Coding; pinned: boolean }) {
  const system = coding.system
    .replace("http://", "")
    .replace("https://", "")
    .replace("urn:harmonization:", "")
    .replace("terminology.hl7.org/CodeSystem/", "");

  const conf = coding.confidence;
  let chipClass: string;
  if (!pinned) {
    chipClass = "info";
  } else if (!conf || conf === "high") {
    chipClass = "accent";
  } else if (conf === "medium") {
    chipClass = "warn";
  } else {
    chipClass = "err";
  }

  const confLabel = conf && conf !== "high" ? ` [${conf} confidence]` : "";

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, maxWidth: "100%" }}>
      <span
        className={cx("chip mono", chipClass)}
        title={`${coding.system} · ${coding.code}${confLabel}`}
        style={{ minWidth: 0 }}
      >
        {conf === "low" && "⚠ "}
        {system} · {coding.code}
        {coding.display ? ` · ${coding.display}` : ""}
        {conf === "medium" && " ?"}
      </span>
      <StandardBadge value={coding.standard_concept} />
    </span>
  );
}

function CategorySelect({
  value,
  onChange,
}: {
  value: Coding | null;
  onChange: (coding: Coding | null) => void;
}) {
  const current = value?.code ?? "";
  return (
    <select
      className="select"
      value={current}
      onChange={(e) => {
        const code = e.target.value;
        const found = CATEGORY_OPTIONS.find((o) => o.code === code) ?? null;
        onChange(found);
      }}
      style={{ minWidth: 180, fontSize: 12 }}
    >
      <option value="">(unbound)</option>
      {CATEGORY_OPTIONS.map((o) => (
        <option key={o.code} value={o.code}>
          {o.code} — {o.display}
        </option>
      ))}
    </select>
  );
}

function SearchBox({
  initialSystem,
  vocabularies,
  initialQuery,
  onPick,
}: {
  initialSystem: TerminologySystem;
  vocabularies: TerminologySystem[];
  initialQuery: string;
  onPick: (c: Coding) => void;
}) {
  const [system, setSystem] = useState<TerminologySystem>(initialSystem);
  const [q, setQ] = useState(initialQuery);
  const [results, setResults] = useState<Coding[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const trimmed = q.trim();
    if (!trimmed) {
      setResults(null);
      return;
    }
    const my = ++seq.current;
    setLoading(true);
    setError(null);
    const timer = setTimeout(() => {
      searchTerminology(system, trimmed, 20)
        .then((r) => {
          if (seq.current === my) {
            setResults(r);
            setLoading(false);
          }
        })
        .catch((e: Error) => {
          if (seq.current === my) {
            setError(e.message);
            setResults([]);
            setLoading(false);
          }
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [q, system]);

  return (
    <div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
        {vocabularies.length > 1 && (
          <div style={{ display: "flex", gap: 4 }}>
            {vocabularies.map((v) => (
              <button
                key={v}
                className={cx("btn tiny", system === v && "primary")}
                onClick={() => setSystem(v)}
                title={`Semantic search ${SYSTEM_LABEL[v]} via OMOPHub`}
              >
                {SYSTEM_LABEL[v]}
              </button>
            ))}
          </div>
        )}
        <input
          className="input"
          autoFocus
          placeholder={`Semantic search ${SYSTEM_LABEL[system]}…`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ flex: 1, fontSize: 13 }}
        />
      </div>
      <div style={{ marginTop: 4, maxHeight: 240, overflow: "auto" }}>
        {loading && <div className="muted" style={{ fontSize: 12 }}>Semantic searching…</div>}
        {error && (
          <div className="qflag err">
            <div className="qf-bar" />
            <div>
              <div className="qf-code">TERMINOLOGY_LOOKUP_FAILED</div>
              <div className="qf-msg">{error}</div>
            </div>
          </div>
        )}
        {!loading && results && results.length === 0 && !error && (
          <div className="muted" style={{ fontSize: 12 }}>No matches.</div>
        )}
        {results &&
          results.map((r) => (
            <button
              key={`${r.system}|${r.code}`}
              className="btn ghost"
              onClick={() => onPick(r)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                textAlign: "left",
                marginBottom: 4,
                fontSize: 12,
                padding: "6px 8px",
              }}
              title={`${r.system} · ${r.code}`}
            >
              <span className="mono" style={{ color: "var(--ink-3)" }}>{r.code}</span>
              <span style={{ flex: 1, minWidth: 0 }}>{r.display ?? ""}</span>
              <StandardBadge value={r.standard_concept} />
            </button>
          ))}
      </div>
    </div>
  );
}

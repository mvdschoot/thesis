"use client";

import { useCallback, useEffect, useState } from "react";

import { cx } from "@/lib/cx";
import {
  countResource,
  FHIR_BASE,
  searchResources,
} from "@/lib/fhirServer";

type Resource = { resourceType?: string; id?: string } & Record<string, unknown>;

const SUMMARY_TYPES = [
  "Patient",
  "Observation",
  "Device",
  "Questionnaire",
  "QuestionnaireResponse",
  "Provenance",
] as const;

const TABLE_PAGE = 50;

interface CodeableConcept {
  text?: string;
  coding?: { code?: string; display?: string; system?: string }[];
}

function ccText(cc: CodeableConcept | CodeableConcept[] | undefined): string {
  const one = Array.isArray(cc) ? cc[0] : cc;
  if (!one) return "—";
  return one.text ?? one.coding?.[0]?.display ?? one.coding?.[0]?.code ?? "—";
}

function obsValue(r: Resource): string {
  const q = r.valueQuantity as { value?: number; unit?: string } | undefined;
  if (q && q.value !== undefined) return `${q.value}${q.unit ? ` ${q.unit}` : ""}`;
  if (typeof r.valueBoolean === "boolean") return String(r.valueBoolean);
  if (typeof r.valueString === "string") return r.valueString;
  if (Array.isArray(r.component)) return `${r.component.length} components`;
  return "—";
}

function effective(r: Resource): string {
  if (typeof r.effectiveDateTime === "string") return r.effectiveDateTime;
  const p = r.effectivePeriod as { start?: string } | undefined;
  return p?.start ?? "—";
}

function subjectRef(r: Resource): string {
  const s = r.subject as { reference?: string } | undefined;
  return s?.reference ?? "—";
}

function patientLabel(r: Resource): string {
  const idents = r.identifier as { value?: string }[] | undefined;
  return idents?.[0]?.value ?? r.id ?? "—";
}

export default function FhirServerPanel() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [patients, setPatients] = useState<Resource[]>([]);
  const [observations, setObservations] = useState<Resource[]>([]);
  const [subjectFilter, setSubjectFilter] = useState<{ id: string; label: string } | null>(null);
  const [selected, setSelected] = useState<Resource | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadObservations = useCallback(async (filterId: string | null) => {
    const bundle = await searchResources("Observation", {
      _count: TABLE_PAGE,
      _sort: "-_lastUpdated",
      subject: filterId ? `Patient/${filterId}` : undefined,
    });
    setObservations((bundle.entry ?? []).map((e) => e.resource as Resource));
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [countPairs, patientBundle] = await Promise.all([
        Promise.all(
          SUMMARY_TYPES.map(async (t) => [t, await countResource(t)] as const),
        ),
        searchResources("Patient", { _count: TABLE_PAGE }),
      ]);
      setCounts(Object.fromEntries(countPairs));
      setPatients((patientBundle.entry ?? []).map((e) => e.resource as Resource));
      await loadObservations(subjectFilter?.id ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [loadObservations, subjectFilter]);

  // Initial load.
  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectPatient(r: Resource) {
    const id = r.id;
    if (!id) return;
    const next = { id, label: patientLabel(r) };
    setSubjectFilter(next);
    setSelected(r);
    void loadObservations(id);
  }

  function clearFilter() {
    setSubjectFilter(null);
    void loadObservations(null);
  }

  return (
    <div>
      <div className="section-sub">FHIR Server · live HAPI R4 endpoint</div>
      <h2 className="section-title">FHIR Server</h2>
      <p className="muted" style={{ maxWidth: 720, marginTop: 0 }}>
        Browsing the HAPI FHIR server directly at <span className="mono">{FHIR_BASE}</span> — no
        backend proxy. Export bundles from the <span className="mono">FHIR Bundle</span> tab, then
        refresh here.
      </p>

      <div style={{ display: "flex", gap: 8, margin: "12px 0", alignItems: "center" }}>
        <button className="btn" onClick={() => void refresh()} disabled={loading}>
          {loading ? (
            <>
              <span className="spin" /> Loading…
            </>
          ) : (
            <>Refresh</>
          )}
        </button>
      </div>

      {error && (
        <div className="qflag err" style={{ marginBottom: 16 }}>
          <div className="qf-bar" />
          <div>
            <div className="qf-code">FHIR_SERVER_UNREACHABLE</div>
            <div className="qf-msg">{error}</div>
          </div>
        </div>
      )}

      {counts && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <span className="eyebrow">Resource counts</span>
          </div>
          <div className="card-body" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {SUMMARY_TYPES.map((t) => (
              <span key={t} className="chip mono">
                {counts[t] ?? 0} {t}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <span className="eyebrow">Patients</span>
          <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
            {patients.length} shown
          </span>
        </div>
        <div style={{ maxHeight: 300, overflow: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>id</th>
                <th>identifier</th>
              </tr>
            </thead>
            <tbody>
              {patients.length === 0 ? (
                <tr>
                  <td colSpan={2} className="muted">
                    No patients on the server yet.
                  </td>
                </tr>
              ) : (
                patients.map((p) => (
                  <tr
                    key={p.id}
                    className={cx(subjectFilter?.id === p.id && "selected")}
                    onClick={() => selectPatient(p)}
                  >
                    <td className="mono">{p.id}</td>
                    <td className="mono">{patientLabel(p)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <span className="eyebrow">Observations</span>
          {subjectFilter && (
            <span className="chip mono" style={{ marginLeft: 10 }}>
              subject: {subjectFilter.label}
              <button
                type="button"
                onClick={clearFilter}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "inherit",
                  cursor: "pointer",
                  marginLeft: 6,
                  padding: 0,
                  font: "inherit",
                }}
                title="Clear patient filter"
              >
                ✕
              </button>
            </span>
          )}
          <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
            {observations.length} shown
          </span>
        </div>
        <div style={{ maxHeight: 420, overflow: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>code</th>
                <th>category</th>
                <th>value</th>
                <th>effective</th>
                <th>status</th>
                <th>subject</th>
              </tr>
            </thead>
            <tbody>
              {observations.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    No observations{subjectFilter ? " for this patient" : ""}.
                  </td>
                </tr>
              ) : (
                observations.map((o) => (
                  <tr
                    key={o.id}
                    className={cx(selected?.id === o.id && "selected")}
                    onClick={() => setSelected(o)}
                  >
                    <td>{ccText(o.code as CodeableConcept)}</td>
                    <td className="mono muted">{ccText(o.category as CodeableConcept[])}</td>
                    <td className="mono">{obsValue(o)}</td>
                    <td className="mono">{effective(o)}</td>
                    <td>
                      <span className="chip">{String(o.status ?? "—")}</span>
                    </td>
                    <td className="mono muted">{subjectRef(o)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <span className="eyebrow">
              {String(selected.resourceType ?? "Resource")} · <span className="mono">{selected.id}</span>
            </span>
            <button className="btn" style={{ marginLeft: "auto" }} onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <div className="card-body">
            <pre className="code-pre" style={{ maxHeight: 420, fontSize: 12, overflow: "auto" }}>
              {JSON.stringify(selected, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

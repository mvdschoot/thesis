"use client";

import { useMemo, useState } from "react";

import { cx } from "@/lib/cx";
import type { OmopCdmOutput } from "@/lib/types";

type OmopTable = "measurement" | "observation" | "person" | "device_exposure" | "observation_period";

const TABLE_LABELS: Record<OmopTable, string> = {
  measurement: "measurement",
  observation: "observation",
  person: "person",
  device_exposure: "device_exposure",
  observation_period: "observation_period",
};

interface Props {
  cdm: OmopCdmOutput | null;
}

function toCsv(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const keys = Object.keys(rows[0]);
  const header = keys.join(",");
  const body = rows.map((r) =>
    keys
      .map((k) => {
        const v = r[k];
        if (v === null || v === undefined) return "";
        const s = String(v);
        return s.includes(",") || s.includes('"') || s.includes("\n")
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      })
      .join(","),
  );
  return [header, ...body].join("\n");
}

function downloadCsv(rows: Record<string, unknown>[], filename: string) {
  const csv = toCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadJson(data: unknown, filename: string) {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const MAX_PREVIEW_ROWS = 100;

export default function OmopCdmPanel({ cdm }: Props) {
  const [activeTable, setActiveTable] = useState<OmopTable>("measurement");
  const [copiedTable, setCopiedTable] = useState<string | null>(null);

  const tableCounts = useMemo(() => {
    if (!cdm) return {} as Record<OmopTable, number>;
    return {
      measurement: cdm.measurement?.length ?? 0,
      observation: cdm.observation?.length ?? 0,
      person: cdm.person?.length ?? 0,
      device_exposure: cdm.device_exposure?.length ?? 0,
      observation_period: cdm.observation_period?.length ?? 0,
    };
  }, [cdm]);

  const activeRows = useMemo(() => {
    if (!cdm) return [];
    return (cdm[activeTable] ?? []) as Record<string, unknown>[];
  }, [cdm, activeTable]);

  const columns = useMemo(() => {
    if (activeRows.length === 0) return [];
    return Object.keys(activeRows[0]);
  }, [activeRows]);

  if (!cdm) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-body">
          <p className="muted">
            OMOP CDM output disabled — set{" "}
            <span className="mono">omop.enabled: true</span> in the active
            pipeline config (or include an <span className="mono">omop:</span>{" "}
            block at all) to populate this view.
          </p>
        </div>
      </div>
    );
  }

  const resStats = cdm.resolution_stats;
  const unmappedCount = cdm.unmapped?.length ?? 0;

  function copyTable() {
    const json = JSON.stringify(activeRows, null, 2);
    void navigator.clipboard?.writeText(json).then(
      () => {
        setCopiedTable(activeTable);
        setTimeout(() => setCopiedTable(null), 1400);
      },
      () => setCopiedTable(null),
    );
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <span className="eyebrow">
          OMOP CDM v5.4 ·{" "}
          {(tableCounts.measurement ?? 0) + (tableCounts.observation ?? 0)} clinical rows ·{" "}
          {tableCounts.person ?? 0} person(s)
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            className="btn"
            onClick={copyTable}
            title={`Copy ${activeTable} JSON to clipboard`}
          >
            {copiedTable === activeTable ? "Copied" : "Copy JSON"}
          </button>
          <button
            className="btn"
            onClick={() => downloadCsv(activeRows, `${activeTable}.csv`)}
            title={`Download ${activeTable}.csv`}
          >
            CSV
          </button>
          <button
            className="btn"
            onClick={() => downloadJson(cdm, "omop_cdm.json")}
            title="Download all OMOP CDM tables as JSON"
          >
            Download All
          </button>
        </div>
      </div>

      <div className="card-body">
        {/* Resolution summary */}
        {resStats && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            <span className={cx("chip mono", resStats.resolved > 0 ? "ok" : "info")}>
              {resStats.resolved}/{resStats.total_codings} resolved
            </span>
            {Object.entries(resStats.mapping_types ?? {}).map(([type, count]) =>
              count > 0 ? (
                <span key={type} className="chip mono">
                  {count} {type}
                </span>
              ) : null,
            )}
            {unmappedCount > 0 && (
              <span className="chip mono warn">{unmappedCount} unmapped events</span>
            )}
          </div>
        )}

        {/* Table selector */}
        <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          {(Object.keys(TABLE_LABELS) as OmopTable[]).map((table) => (
            <button
              key={table}
              className={cx("btn", activeTable === table && "primary")}
              onClick={() => setActiveTable(table)}
              style={{ fontSize: 12 }}
            >
              <span className="mono">{TABLE_LABELS[table]}</span>{" "}
              ({tableCounts[table] ?? 0})
            </button>
          ))}
        </div>

        {/* Table grid */}
        {activeRows.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>
            No rows in <span className="mono">{activeTable}</span>.
          </p>
        ) : (
          <div style={{ overflow: "auto", maxHeight: 520 }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col}
                      style={{
                        textAlign: "left",
                        padding: "6px 10px",
                        borderBottom: "1px solid var(--border, #333)",
                        whiteSpace: "nowrap",
                        position: "sticky",
                        top: 0,
                        background: "var(--bg-card, #1a1a1a)",
                        fontFamily: "var(--font-mono, monospace)",
                        fontWeight: 600,
                      }}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activeRows.slice(0, MAX_PREVIEW_ROWS).map((row, i) => (
                  <tr key={i}>
                    {columns.map((col) => (
                      <td
                        key={col}
                        style={{
                          padding: "4px 10px",
                          borderBottom: "1px solid var(--border-dim, #222)",
                          whiteSpace: "nowrap",
                          maxWidth: 260,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          fontFamily: "var(--font-mono, monospace)",
                        }}
                        title={String(row[col] ?? "")}
                      >
                        {row[col] === null || row[col] === undefined
                          ? ""
                          : String(row[col])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {activeRows.length > MAX_PREVIEW_ROWS && (
              <p className="help" style={{ marginTop: 8 }}>
                Showing first {MAX_PREVIEW_ROWS} of {activeRows.length} rows ·
                use CSV download for the full table.
              </p>
            )}
          </div>
        )}

        {/* Unmapped events detail */}
        {unmappedCount > 0 && (
          <details style={{ marginTop: 12 }}>
            <summary
              style={{ cursor: "pointer", fontSize: 13 }}
              className="muted"
            >
              {unmappedCount} unmapped event(s) — concept_id = 0
            </summary>
            <pre
              className="code-pre"
              style={{ maxHeight: 200, fontSize: 11, marginTop: 8, overflow: "auto" }}
            >
              {JSON.stringify(cdm.unmapped, null, 2)}
            </pre>
          </details>
        )}

        <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
          Table routing is domain-driven via OMOPHub FHIR Resolver. Bind concepts
          in the <span className="mono">Concepts</span> tab and re-transform to
          resolve <span className="mono">concept_id</span> values and route events
          to the correct CDM tables.
        </p>
      </div>
    </div>
  );
}

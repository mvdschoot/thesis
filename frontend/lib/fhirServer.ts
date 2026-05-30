"use client";

import type { FhirBundle, FhirBundleEntry } from "./types";

// The frontend talks to the HAPI FHIR server directly (no backend proxy).
// Baked at build time via the NEXT_PUBLIC_FHIR_BASE_URL Dockerfile ARG, same
// pattern as NEXT_PUBLIC_API_BASE_URL in lib/api.ts.
export const FHIR_BASE =
  process.env.NEXT_PUBLIC_FHIR_BASE_URL ?? "http://localhost:8080/fhir";

const FHIR_JSON = "application/fhir+json";

/** Pull a human-readable message out of an OperationOutcome (or fall back). */
function outcomeMessage(body: unknown, fallback: string): string {
  const issues = (body as { issue?: unknown[] })?.issue;
  if (Array.isArray(issues) && issues.length > 0) {
    const first = issues[0] as {
      diagnostics?: string;
      details?: { text?: string };
    };
    return first.diagnostics ?? first.details?.text ?? fallback;
  }
  return fallback;
}

async function fhirFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${FHIR_BASE}${path}`, {
    ...init,
    headers: { Accept: FHIR_JSON, ...(init.headers ?? {}) },
  });
  const text = await res.text();
  const body = text ? (JSON.parse(text) as unknown) : null;
  if (!res.ok) {
    throw new Error(outcomeMessage(body, `${res.status} ${res.statusText}`));
  }
  return body as T;
}

export interface ExportSummary {
  total: number;
  ok: number;
  errors: { entry: number; status: string; detail: string }[];
}

/**
 * POST the bundle to the FHIR server. Every entry is rewritten to a
 * `PUT {ResourceType}/{id}` request so re-exporting the same dataset upserts
 * (idempotent) rather than creating duplicates — safe because the builder
 * assigns each resource a deterministic id.
 */
export async function exportBundle(bundle: FhirBundle): Promise<ExportSummary> {
  const entries: FhirBundleEntry[] = (bundle.entry ?? []).map((e) => {
    const resourceType = e.resource.resourceType;
    const id = e.resource.id as string | undefined;
    return {
      ...e,
      request:
        id != null
          ? { method: "PUT", url: `${resourceType}/${id}` }
          : { method: "POST", url: resourceType },
    };
  });

  const txn: FhirBundle = { resourceType: "Bundle", type: "transaction", entry: entries };

  interface TxnResponseBundle {
    entry?: { response?: { status?: string } }[];
  }
  const result = await fhirFetch<TxnResponseBundle>("", {
    method: "POST",
    headers: { "Content-Type": FHIR_JSON },
    body: JSON.stringify(txn),
  });

  const responseEntries = result.entry ?? [];
  const errors: ExportSummary["errors"] = [];
  let ok = 0;
  responseEntries.forEach((e, i) => {
    const status = e.response?.status ?? "";
    if (/^2\d\d/.test(status)) {
      ok += 1;
    } else {
      errors.push({ entry: i, status, detail: status || "no status" });
    }
  });

  return { total: entries.length, ok, errors };
}

/** Count resources of a type via `_summary=count` → Bundle.total. */
export async function countResource(resourceType: string): Promise<number> {
  const b = await fhirFetch<{ total?: number }>(
    `/${resourceType}?_summary=count`,
  );
  return b.total ?? 0;
}

/** Search a resource type; returns the raw search Bundle. */
export async function searchResources(
  resourceType: string,
  params: Record<string, string | number | undefined> = {},
): Promise<FhirBundle> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  const q = qs.toString();
  return fhirFetch<FhirBundle>(`/${resourceType}${q ? `?${q}` : ""}`);
}

/** Read a single resource by id. */
export async function readResource<T = Record<string, unknown>>(
  resourceType: string,
  id: string,
): Promise<T> {
  return fhirFetch<T>(`/${resourceType}/${encodeURIComponent(id)}`);
}

"use client";

import { useEffect, useMemo, useState } from "react";

import {
  listConfigs,
  matchConfigs,
  type ConfigMatch,
  type ConfigSummary,
} from "@/lib/api";

interface Props {
  data: unknown | null;
  source: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  refreshKey?: number;
}

type MatchBadge =
  | { tone: "none"; label: string }
  | { tone: "good"; label: string }
  | { tone: "warn"; label: string }
  | { tone: "bad"; label: string };

function badgeFor(match: ConfigMatch | undefined, hasData: boolean): MatchBadge {
  if (!match) return { tone: "none", label: hasData ? "—" : "No input yet" };
  if (match.error) return { tone: "bad", label: match.error };
  if (match.applicable) {
    return {
      tone: "good",
      label: `Applicable (${match.matched_records}/${match.total_records} records)`,
    };
  }
  if (!match.source_match_known) {
    return {
      tone: "warn",
      label: `Source unknown — ${match.matched_records}/${match.total_records} records match`,
    };
  }
  if (!match.source_match) return { tone: "bad", label: "Source mismatch" };
  return { tone: "bad", label: "No records match" };
}

const toneClass: Record<MatchBadge["tone"], string> = {
  good: "bg-green-100 text-green-800",
  warn: "bg-yellow-100 text-yellow-800",
  bad: "bg-gray-100 text-gray-600",
  none: "bg-gray-50 text-gray-500",
};

export default function ConfigBrowser({
  data,
  source,
  selectedId,
  onSelect,
  refreshKey,
}: Props) {
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [matches, setMatches] = useState<ConfigMatch[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [matchLoading, setMatchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    listConfigs()
      .then((cfgs) => {
        if (!cancelled) setConfigs(cfgs);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    if (!data) {
      setMatches([]);
      return;
    }
    let cancelled = false;
    setMatchLoading(true);
    matchConfigs(data, source.trim() || undefined)
      .then((m) => {
        if (!cancelled) setMatches(m);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setMatchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data, source]);

  const matchById = useMemo(() => {
    const m = new Map<string, ConfigMatch>();
    for (const x of matches) m.set(x.id, x);
    return m;
  }, [matches]);

  const sorted = useMemo(() => {
    if (!data) return configs;
    return [...configs].sort((a, b) => {
      const ma = matchById.get(a.id);
      const mb = matchById.get(b.id);
      const aScore = ma?.applicable ? 1 : 0;
      const bScore = mb?.applicable ? 1 : 0;
      if (aScore !== bScore) return bScore - aScore;
      const aRec = ma?.matched_records ?? 0;
      const bRec = mb?.matched_records ?? 0;
      if (aRec !== bRec) return bRec - aRec;
      return a.id.localeCompare(b.id);
    });
  }, [configs, matchById, data]);

  const hasData = data != null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600">
          {listLoading
            ? "Loading configs…"
            : `${configs.length} config${configs.length === 1 ? "" : "s"} available`}
          {matchLoading && " · checking matches…"}
        </p>
      </div>
      {error && (
        <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>
      )}
      {!listLoading && configs.length === 0 && (
        <p className="text-sm text-gray-600">
          No configs yet. Generate one to populate the list.
        </p>
      )}
      <ul className="divide-y rounded border border-gray-200">
        {sorted.map((cfg) => {
          const match = matchById.get(cfg.id);
          const badge = badgeFor(match, hasData);
          const selected = cfg.id === selectedId;
          return (
            <li key={cfg.id}>
              <button
                type="button"
                onClick={() => onSelect(cfg.id)}
                className={`flex w-full flex-col gap-1 px-3 py-2 text-left hover:bg-gray-50 ${
                  selected ? "bg-blue-50" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm">{cfg.id}</span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${toneClass[badge.tone]}`}
                  >
                    {badge.label}
                  </span>
                </div>
                <div className="text-xs text-gray-600">
                  {cfg.description || <em>no description</em>}
                  {cfg.source && (
                    <>
                      {" · source="}
                      <span className="font-mono">{cfg.source}</span>
                    </>
                  )}
                  {cfg.version && <> · v{cfg.version}</>}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

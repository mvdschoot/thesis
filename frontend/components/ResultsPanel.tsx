"use client";

import type { TransformResponse } from "@/lib/api";

interface Props {
  result: TransformResponse | null;
  yaml: string;
}

function download(filename: string, contents: string, mime: string) {
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ResultsPanel({ result, yaml }: Props) {
  if (!result) return null;

  const { events, stats } = result;
  const flaggedCount = Object.values(stats.flags).reduce((a, b) => a + b, 0);
  const eventsJson = JSON.stringify(events, null, 2);

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">4. Results</h2>
      <p className="text-sm">
        {stats.count} events across {stats.subjects.length} subjects
        {flaggedCount > 0 &&
          `, ${flaggedCount} flag occurrences (${Object.entries(stats.flags)
            .map(([k, v]) => `${k}: ${v}`)
            .join(", ")})`}
        .
      </p>

      <div className="flex gap-2">
        <button
          onClick={() => download("events.json", eventsJson, "application/json")}
          className="rounded bg-black px-3 py-1 text-sm text-white"
        >
          Download events.json
        </button>
        <button
          onClick={() => download("config.yaml", yaml, "text/yaml")}
          className="rounded border border-black px-3 py-1 text-sm"
        >
          Download config.yaml
        </button>
        <button
          onClick={() => navigator.clipboard.writeText(yaml)}
          className="rounded border border-gray-400 px-3 py-1 text-sm"
        >
          Copy YAML
        </button>
      </div>

      <details className="rounded border border-gray-200 bg-white" open>
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
          events.json (preview)
        </summary>
        <pre className="max-h-[500px] overflow-auto p-3 text-xs leading-5">
          {eventsJson}
        </pre>
      </details>
    </section>
  );
}

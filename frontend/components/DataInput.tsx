"use client";

import { useState } from "react";

interface Props {
  data: unknown | null;
  onChange: (next: unknown | null) => void;
}

type Tab = "upload" | "paste";

export default function DataInput({ data, onChange }: Props) {
  const [tab, setTab] = useState<Tab>("upload");
  const [fileName, setFileName] = useState<string | null>(null);
  const [pasted, setPasted] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setFileName(file.name);
    try {
      const text = await file.text();
      onChange(JSON.parse(text));
    } catch (e) {
      setError(`Invalid JSON: ${(e as Error).message}`);
      onChange(null);
    }
  }

  function validatePaste() {
    setError(null);
    try {
      onChange(JSON.parse(pasted));
    } catch (e) {
      setError(`Invalid JSON: ${(e as Error).message}`);
      onChange(null);
    }
  }

  const summary = data
    ? Array.isArray(data)
      ? `parsed array (${data.length} top-level items)`
      : `parsed object (${Object.keys(data as object).length} top-level keys)`
    : null;

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">1. Input data</h2>
      <div className="flex gap-2 border-b">
        {(["upload", "paste"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1 text-sm ${
              tab === t ? "border-b-2 border-black font-medium" : "text-gray-500"
            }`}
          >
            {t === "upload" ? "Upload file" : "Paste JSON"}
          </button>
        ))}
      </div>

      {tab === "upload" ? (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) handleFile(f);
          }}
          className="rounded border-2 border-dashed border-gray-300 p-6 text-center"
        >
          <input
            type="file"
            accept=".json,application/json"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
            className="block mx-auto"
          />
          <p className="mt-2 text-xs text-gray-500">
            Or drop a .json file anywhere inside this box.
          </p>
          {fileName && <p className="mt-2 text-sm">Loaded: {fileName}</p>}
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            rows={10}
            placeholder='{"example": "paste your JSON here"}'
            className="w-full rounded border p-2 font-mono text-sm"
          />
          <button
            onClick={validatePaste}
            className="rounded bg-gray-800 px-3 py-1 text-sm text-white"
          >
            Validate JSON
          </button>
        </div>
      )}

      {summary && (
        <p className="text-sm text-green-700">Loaded: {summary}</p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}

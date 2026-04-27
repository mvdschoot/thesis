"use client";

import dynamic from "next/dynamic";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export type SaveStatus = "idle" | "saving" | "saved" | "error" | "dirty";

interface Props {
  value: string;
  onChange: (v: string) => void;
  status?: SaveStatus;
  statusMessage?: string;
}

const STATUS_STYLES: Record<SaveStatus, { label: string; className: string }> = {
  idle: { label: "", className: "text-gray-500" },
  dirty: { label: "Unsaved changes", className: "text-amber-700" },
  saving: { label: "Saving…", className: "text-gray-600" },
  saved: { label: "Saved", className: "text-green-700" },
  error: { label: "Save failed", className: "text-red-700" },
};

export default function YamlEditor({
  value,
  onChange,
  status = "idle",
  statusMessage,
}: Props) {
  const s = STATUS_STYLES[status];
  return (
    <div className="space-y-1">
      {(s.label || statusMessage) && (
        <div className={`text-xs ${s.className}`}>
          {s.label}
          {statusMessage && status === "error" ? `: ${statusMessage}` : ""}
        </div>
      )}
      <div className="rounded border border-gray-300">
        <Editor
          height="500px"
          defaultLanguage="yaml"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            tabSize: 2,
            wordWrap: "on",
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  );
}

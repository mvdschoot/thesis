"use client";

import dynamic from "next/dynamic";

const MonacoDiff = dynamic(
  () => import("@monaco-editor/react").then((m) => m.DiffEditor),
  {
    ssr: false,
    loading: () => (
      <div className="yaml-block" style={{ minHeight: 320, color: "var(--ink-3)" }}>
        Loading diff…
      </div>
    ),
  },
);

interface Props {
  original: string;
  modified: string;
  height?: number | string;
}

export default function YamlDiffEditor({ original, modified, height = 520 }: Props) {
  return (
    <div
      style={{
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
    >
      <MonacoDiff
        height={height}
        language="yaml"
        original={original}
        modified={modified}
        options={{
          minimap: { enabled: false },
          fontSize: 12,
          fontFamily: "var(--font-mono)",
          renderSideBySide: true,
          readOnly: true,
          scrollBeyondLastLine: false,
          automaticLayout: true,
        }}
      />
    </div>
  );
}

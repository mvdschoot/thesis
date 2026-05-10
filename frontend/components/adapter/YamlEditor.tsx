"use client";

import dynamic from "next/dynamic";

const Monaco = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="yaml-block" style={{ minHeight: 320, color: "var(--ink-3)" }}>
      Loading editor…
    </div>
  ),
});

interface Props {
  value: string;
  onChange: (next: string) => void;
  height?: number | string;
  readOnly?: boolean;
}

export default function YamlEditor({ value, onChange, height = 520, readOnly }: Props) {
  return (
    <div
      style={{
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
    >
      <Monaco
        height={height}
        defaultLanguage="yaml"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          minimap: { enabled: false },
          fontSize: 12,
          fontFamily: "var(--font-mono)",
          tabSize: 2,
          insertSpaces: true,
          wordWrap: "on",
          scrollBeyondLastLine: false,
          renderWhitespace: "selection",
          readOnly: readOnly === true,
          automaticLayout: true,
        }}
      />
    </div>
  );
}

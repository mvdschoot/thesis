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
        // Don't let @monaco-editor/react dispose the underlying TextModels when
        // the diff unmounts (e.g. on Apply/Discard). The wrapper disposes them
        // in an order that trips Monaco's "TextModel got disposed before
        // DiffEditorWidget model got reset" assertion. Keeping the models lets
        // the editor reset cleanly; the small per-diff model retention is
        // negligible for this occasional AI-proposal view.
        keepCurrentOriginalModel
        keepCurrentModifiedModel
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

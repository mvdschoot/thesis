"use client";

import { useRef, useState } from "react";

import { generateConfig, type Descriptor } from "@/lib/api";
import { cx } from "@/lib/cx";

type DialogStage = "input" | "thinking" | "done" | "error";

const DESCRIPTOR_ACCEPT = ".json,.avsc,.avro,.md,.markdown,.txt,.yaml,.yml,.csv,.xml";

interface Props {
  data: unknown | null;
  source: string;
  onClose: () => void;
  onApply: (yamlText: string, configId: string, descriptors: Descriptor[]) => void;
}

export default function LLMDialog({ data, source, onClose, onApply }: Props) {
  const [stage, setStage] = useState<DialogStage>("input");
  const [description, setDescription] = useState("");
  const [hint, setHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<{ id: string; yaml: string } | null>(null);
  const [descriptors, setDescriptors] = useState<Descriptor[]>([]);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function addFiles(files: FileList | File[]) {
    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result;
        if (typeof result !== "string") return;
        setDescriptors((prev) => {
          // Replace a same-named file rather than stacking duplicates.
          const next = prev.filter((d) => d.filename !== file.name);
          return [...next, { filename: file.name, content: result }];
        });
      };
      reader.readAsText(file);
    });
  }

  function removeDescriptor(filename: string) {
    setDescriptors((prev) => prev.filter((d) => d.filename !== filename));
  }

  async function run() {
    if (!data) {
      setError("Load some data in the Connector stage first.");
      setStage("error");
      return;
    }
    if (!description.trim()) {
      setError("Add a description so the LLM knows what this data is.");
      setStage("error");
      return;
    }
    setStage("thinking");
    try {
      const res = await generateConfig({
        data,
        description,
        hints: hint || undefined,
        source: source || undefined,
        descriptors: descriptors.length ? descriptors : undefined,
      });
      setGenerated(res);
      setStage("done");
    } catch (e) {
      setError((e as Error).message);
      setStage("error");
    }
  }

  return (
    <>
      <div className="scrim open" onClick={onClose} />
      <div className="dialog">
        <div className="dialog-head">
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            POST /api/generate-config
          </div>
          <h3>Generate adapter from sample record</h3>
        </div>
        <div className="dialog-body">
          {stage === "input" && (
            <>
              {/* <div className="spacer-sm" /> */}
              <div className="field">
                <label>description</label>
                <textarea
                  className="textarea"
                  rows={3}
                  value={description}
                  placeholder="What does each record represent? Subject field? Quirks?"
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="field">
                <label>Hint (optional)</label>
                <textarea
                  className="textarea"
                  rows={2}
                  value={hint}
                  placeholder='e.g. "iterate over results array; treat email as subject_id"'
                  onChange={(e) => setHint(e.target.value)}
                />
              </div>
              <div className="field">
                <label>Descriptor files (optional)</label>
                <div
                  className={cx("dropzone", drag && "dragover")}
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
                  }}
                >
                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    Drop schema / spec files (JSON Schema, Avro, markdown…) or click to browse
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    Passed to the LLM as extra context and saved with the config.
                  </div>
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    accept={DESCRIPTOR_ACCEPT}
                    onChange={(e) => {
                      if (e.target.files?.length) addFiles(e.target.files);
                      e.target.value = "";
                    }}
                    style={{ display: "none" }}
                  />
                </div>
                {descriptors.length > 0 && (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {descriptors.map((d) => (
                      <div
                        key={d.filename}
                        className="row"
                        style={{ alignItems: "center", gap: 8 }}
                      >
                        <span className="mono" style={{ fontSize: 12, flex: 1, minWidth: 0 }}>
                          {d.filename}
                        </span>
                        <span className="muted" style={{ fontSize: 11 }}>
                          {d.content.length.toLocaleString()} chars
                        </span>
                        <button
                          className="btn"
                          style={{ padding: "2px 8px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            removeDescriptor(d.filename);
                          }}
                          aria-label={`Remove ${d.filename}`}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="help">
                Few-shot corpus: <span className="mono">backend/configs/*.yaml</span> · prompt:{" "}
                <span className="mono">api/prompts.py</span>
              </div>
              <div className="dialog-actions">
                <button className="btn" onClick={onClose}>
                  Cancel
                </button>
                <button className="btn accent" onClick={run}>
                  Generate
                </button>
              </div>
            </>
          )}
          {stage === "thinking" && (
            <div style={{ padding: "24px 0", textAlign: "center" }}>
              <div className="spin" style={{ width: 18, height: 18 }} />
              <div
                style={{
                  marginTop: 12,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--ink-3)",
                }}
              >
                Sampling few-shot configs · prompting…
              </div>
            </div>
          )}
          {stage === "error" && (
            <div>
              <div className="qflag err" style={{ marginBottom: 14 }}>
                <div className="qf-bar" />
                <div>
                  <div className="qf-code">GENERATE_FAILED</div>
                  <div className="qf-msg">{error ?? "Unknown error"}</div>
                </div>
              </div>
              <div className="dialog-actions">
                <button className="btn" onClick={onClose}>
                  Close
                </button>
                <button className="btn accent" onClick={() => setStage("input")}>
                  Retry
                </button>
              </div>
            </div>
          )}
          {stage === "done" && generated && (
            <div>
              <div className="qflag info" style={{ marginBottom: 14 }}>
                <div className="qf-bar" />
                <div>
                  <div className="qf-code">CONFIG_GENERATED</div>
                  <div className="qf-msg">
                    New adapter scaffold ready (id: <span className="mono">{generated.id}</span>). Apply to load it into the editor.
                  </div>
                </div>
              </div>
              <div className="dialog-actions">
                <button className="btn" onClick={onClose}>
                  Close
                </button>
                <button
                  className="btn accent"
                  onClick={() => {
                    onApply(generated.yaml, generated.id, descriptors);
                    onClose();
                  }}
                >
                  Apply to editor
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

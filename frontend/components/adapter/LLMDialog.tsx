"use client";

import { useState } from "react";

import { generateConfig } from "@/lib/api";

type DialogStage = "input" | "thinking" | "done" | "error";

interface Props {
  data: unknown | null;
  source: string;
  onClose: () => void;
  onApply: (yamlText: string, configId: string) => void;
}

export default function LLMDialog({ data, source, onClose, onApply }: Props) {
  const [stage, setStage] = useState<DialogStage>("input");
  const [description, setDescription] = useState("");
  const [hint, setHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<{ id: string; yaml: string } | null>(null);

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
                    onApply(generated.yaml, generated.id);
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

"use client";

import { useEffect, useRef, useState } from "react";

import { editConfig, updateConfig, type ConfigMatch, type Descriptor } from "@/lib/api";
import { cx } from "@/lib/cx";
import type { AdapterConfig } from "@/lib/types";
import { dumpAdapterYaml, parseAdapterYaml } from "@/lib/yaml";

import LLMDialog from "./LLMDialog";
import YamlDiffEditor from "./YamlDiffEditor";
import YamlEditor from "./YamlEditor";

interface Props {
  config: AdapterConfig | null;
  onChange: (next: AdapterConfig) => void;
  configKey: string;
  setConfigKey: (k: string) => void;
  inputData: unknown | null;
  source: string;
  onLLMResult: (yamlText: string, configId: string, descriptors: Descriptor[]) => void;
  /** Descriptor files saved with the active config (read-only display). */
  descriptors?: Descriptor[];
  loading?: boolean;
  loadError?: string | null;
  matches?: ConfigMatch[] | null;
}

export default function AdapterPanel({
  config,
  onChange,
  configKey,
  setConfigKey,
  inputData,
  source,
  onLLMResult,
  descriptors,
  loading,
  loadError,
  matches,
}: Props) {
  const [showLLM, setShowLLM] = useState(false);
  const [openDescriptor, setOpenDescriptor] = useState<string | null>(null);

  // YAML editor state.
  const [yamlText, setYamlText] = useState<string>("");
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [savedYaml, setSavedYaml] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // "Edit with AI" state — natural-language YAML editing via the LLM.
  const [showEditBox, setShowEditBox] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [proposed, setProposed] = useState<string | null>(null);

  // Re-seed the buffer once per selected config. Backend configs are
  // lazy-loaded, so `config` may still be null right after `configKey` changes
  // and only arrive asynchronously. Keying off the seeded config id (rather than
  // just `configKey`) lets us seed when the config finally loads, while the ref
  // guard avoids clobbering the user's in-editor edits — those keep `configKey`
  // unchanged and `config` is fed back in via onChange, so we must not re-seed.
  const seededKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!config) return;
    if (seededKeyRef.current === configKey) return;
    seededKeyRef.current = configKey;
    const text = dumpAdapterYaml(config);
    setYamlText(text);
    setSavedYaml(text);
    setYamlError(null);
    setSaveError(null);
    setSavedAt(null);
    setProposed(null);
    setShowEditBox(false);
    setInstruction("");
    setEditError(null);
  }, [configKey, config]);

  // Auto-clear "Saved" toast after 2s.
  useEffect(() => {
    if (savedAt == null) return;
    const t = setTimeout(() => setSavedAt(null), 2000);
    return () => clearTimeout(t);
  }, [savedAt]);

  const handleYamlChange = (next: string) => {
    setYamlText(next);
    try {
      const parsed = parseAdapterYaml(next);
      setYamlError(null);
      onChange(parsed);
    } catch (e) {
      setYamlError((e as Error).message);
    }
  };

  const dirty = yamlText !== savedYaml;
  const canSave = !yamlError && dirty && !saving && config != null;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      await updateConfig(configKey, yamlText);
      setSavedYaml(yamlText);
      setSavedAt(Date.now());
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit() {
    if (!instruction.trim() || editing) return;
    setEditing(true);
    setEditError(null);
    try {
      const res = await editConfig({
        yaml: yamlText,
        instruction,
        sample_data: inputData ?? undefined,
        source: source || undefined,
      });
      setProposed(res.yaml);
      setShowEditBox(false);
    } catch (e) {
      setEditError((e as Error).message);
    } finally {
      setEditing(false);
    }
  }

  function applyProposed() {
    if (proposed === null) return;
    handleYamlChange(proposed);
    setProposed(null);
    setInstruction("");
    setShowEditBox(false);
  }

  return (
    <div>
      <div className="section-sub">Stage 02 · Tier-1 YAML adapter</div>
      <h2 className="section-title">Config</h2>
      <p className="muted" style={{ maxWidth: 700, marginTop: 0 }}>
        A config-driven adapter shapes raw records into{" "}
        <span className="mono">CanonicalEvent</span>s. No source-specific Python — every adapter is YAML.
        Pick an existing one, edit it visually, or generate a new config with an LLM from a record.
      </p>

      <div className="row" style={{ marginTop: 20, alignItems: "center", gap: 12 }}>
        <div className="muted" style={{ fontSize: 12, flex: 1 }}>
          {loading
            ? "Loading config…"
            : loadError
            ? loadError
            : configKey
            ? `Editing ${configKey}.yaml`
            : "Pick a config from the topbar to start."}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => setShowLLM(true)}>
            <span
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--accent)",
              }}
            />
            Generate with LLM
          </button>
        </div>
      </div>

      {matches && (
        <>
          <div className="spacer-sm" />
          <div className="card">
            <div className="card-head">
              <span className="eyebrow">Matching configs</span>
              <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
                {matches.filter((m) => m.applicable).length} applicable · {matches.length} total
              </span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {matches.length === 0 ? (
                <div className="empty" style={{ padding: 14 }}>
                  No configs registered.
                </div>
              ) : (
                <div style={{ maxHeight: 220, overflow: "auto" }}>
                  {matches.map((m) => {
                    const active = m.id === configKey;
                    return (
                      <button
                        key={m.id}
                        onClick={() => setConfigKey(m.id)}
                        className={cx("match-row", active && "active")}
                        style={{
                          width: "100%",
                          textAlign: "left",
                          background: active ? "var(--bg-soft)" : "transparent",
                          border: "none",
                          borderBottom: "1px solid var(--line)",
                          padding: "10px 14px",
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          cursor: "pointer",
                          color: "inherit",
                          font: "inherit",
                        }}
                      >
                        <span
                          className={cx("chip", m.applicable ? "accent" : "")}
                          style={{ minWidth: 78, textAlign: "center" }}
                        >
                          {m.applicable ? "applicable" : "no match"}
                        </span>
                        <span className="mono" style={{ minWidth: 0, flexShrink: 0 }}>
                          {m.id}
                        </span>
                        <span className="muted" style={{ fontSize: 12 }}>
                          {m.matched_records}/{m.total_records} records
                        </span>
                        {m.adapter.description && (
                          <span
                            className="muted"
                            style={{
                              fontSize: 12,
                              marginLeft: "auto",
                              minWidth: 0,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                            title={m.adapter.description}
                          >
                            {m.adapter.description.length > 180 ? m.adapter.description.substring(0, 180) + "..." : m.adapter.description}
                          </span>
                        )}
                        {m.error && (
                          <span
                            className="chip"
                            style={{ color: "var(--err)", borderColor: "var(--err)" }}
                            title={m.error}
                          >
                            error
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      <div className="spacer-md" />

      {!config ? (
        <div className="card">
          <div className="card-body empty">
            No adapter config loaded yet. Pick one from the dropdown or generate one with the LLM.
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-head" style={{ padding: "0 18px" }}>
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 0",
              }}
            >
              <span className="eyebrow" style={{ margin: 0 }}>
                {configKey}.yaml · full file
              </span>
              {yamlError ? (
                <span className="chip" style={{ color: "var(--err)", borderColor: "var(--err)" }}>
                  parse error
                </span>
              ) : dirty ? (
                <span className="chip">unsaved</span>
              ) : savedAt ? (
                <span className="chip" style={{ color: "var(--accent)" }}>
                  saved
                </span>
              ) : null}
              <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <button
                  className="btn"
                  onClick={() => setShowEditBox((s) => !s)}
                  disabled={editing || proposed !== null}
                  title="Describe a change in natural language and let the LLM rewrite the YAML."
                >
                  <span
                    style={{
                      display: "inline-block",
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: "var(--accent)",
                    }}
                  />
                  Edit with AI
                </button>
                <button
                  className={cx("btn", canSave && "primary")}
                  disabled={!canSave}
                  onClick={handleSave}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>

          <div className="card-body">
            <>
                {showEditBox && proposed === null && (
                  <div style={{ marginBottom: 12 }}>
                    <textarea
                      className="textarea mono"
                      rows={3}
                      placeholder="Describe the change you want… e.g. “round all timestamps to the start of the day” or “add an omop block targeting the measurement table”"
                      value={instruction}
                      onChange={(e) => setInstruction(e.target.value)}
                      disabled={editing}
                    />
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        className="btn primary"
                        onClick={handleEdit}
                        disabled={editing || !instruction.trim()}
                      >
                        {editing ? "Asking LLM…" : "Send"}
                      </button>
                      <button
                        className="btn"
                        onClick={() => setShowEditBox(false)}
                        disabled={editing}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {editError && (
                  <div className="qflag err" style={{ marginBottom: 12 }}>
                    <div className="qf-bar" />
                    <div>
                      <div className="qf-code">EDIT_REQUEST_FAILED</div>
                      <div className="qf-msg">{editError}</div>
                    </div>
                  </div>
                )}
                {proposed !== null ? (
                  <>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        marginBottom: 10,
                      }}
                    >
                      <span className="chip" style={{ color: "var(--accent)" }}>
                        AI proposal
                      </span>
                      <span className="muted" style={{ fontSize: 12 }}>
                        Review the diff — left is your current YAML, right is the proposed change.
                      </span>
                      <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                        <button className="btn primary" onClick={applyProposed}>
                          Apply to editor
                        </button>
                        <button className="btn" onClick={() => setProposed(null)}>
                          Discard
                        </button>
                      </div>
                    </div>
                    <YamlDiffEditor original={yamlText} modified={proposed} height={520} />
                    <div className="help" style={{ marginTop: 10 }}>
                      Apply copies the proposal into the editor; Save then writes it to{" "}
                      <span className="mono">backend/configs/{configKey}.yaml</span>. Discard
                      keeps your current YAML untouched.
                    </div>
                  </>
                ) : (
                  <>
                    <YamlEditor value={yamlText} onChange={handleYamlChange} height={520} />
                    {yamlError && (
                      <div className="qflag err" style={{ marginTop: 12 }}>
                        <div className="qf-bar" />
                        <div>
                          <div className="qf-code">YAML_PARSE_ERROR</div>
                          <div className="qf-msg">{yamlError}</div>
                        </div>
                      </div>
                    )}
                    {saveError && (
                      <div className="qflag err" style={{ marginTop: 12 }}>
                        <div className="qf-bar" />
                        <div>
                          <div className="qf-code">SAVE_FAILED</div>
                          <div className="qf-msg">{saveError}</div>
                        </div>
                      </div>
                    )}
                    <div className="help" style={{ marginTop: 10 }}>
                      Edits update the visual editor live (when YAML parses). Save writes to{" "}
                      <span className="mono">backend/configs/{configKey}.yaml</span> via PUT
                      /api/configs/{configKey}. Renaming <span className="mono">adapter.id</span> is
                      rejected by the backend.
                    </div>
                  </>
                )}
            </>
          </div>
        </div>
      )}

      {descriptors && descriptors.length > 0 && (
        <>
          <div className="spacer-md" />
          <div className="card">
            <div className="card-head">
              <span className="eyebrow">Descriptor files</span>
              <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>
                {descriptors.length} file{descriptors.length === 1 ? "" : "s"} · sent to the LLM during generation
              </span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {descriptors.map((d) => {
                const open = openDescriptor === d.filename;
                return (
                  <div key={d.filename} style={{ borderBottom: "1px solid var(--line)" }}>
                    <button
                      onClick={() => setOpenDescriptor(open ? null : d.filename)}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        background: "transparent",
                        border: "none",
                        padding: "10px 14px",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        cursor: "pointer",
                        color: "inherit",
                        font: "inherit",
                      }}
                    >
                      <span className="muted" style={{ fontSize: 11, width: 12 }}>
                        {open ? "▾" : "▸"}
                      </span>
                      <span className="mono" style={{ flex: 1, minWidth: 0 }}>
                        {d.filename}
                      </span>
                      <span className="muted" style={{ fontSize: 11 }}>
                        {d.content.length.toLocaleString()} chars
                      </span>
                    </button>
                    {open && (
                      <pre
                        className="mono"
                        style={{
                          margin: 0,
                          padding: "0 14px 14px 36px",
                          fontSize: 12,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                          maxHeight: 320,
                          overflow: "auto",
                        }}
                      >
                        {d.content}
                      </pre>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {showLLM && (
        <LLMDialog
          data={inputData}
          source={source}
          onClose={() => setShowLLM(false)}
          onApply={onLLMResult}
        />
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

import { updateConfig, type ConfigMatch } from "@/lib/api";
import { cx } from "@/lib/cx";
import type { AdapterConfig } from "@/lib/types";
import { dumpAdapterYaml, parseAdapterYaml } from "@/lib/yaml";

import DefaultsEditor from "./DefaultsEditor";
import EmitEditor from "./EmitEditor";
import LLMDialog from "./LLMDialog";
import MatchEditor from "./MatchEditor";
import YamlEditor from "./YamlEditor";

type Tab = "header" | "match" | "defaults" | "emit";

interface Props {
  config: AdapterConfig | null;
  onChange: (next: AdapterConfig) => void;
  configKey: string;
  setConfigKey: (k: string) => void;
  inputData: unknown | null;
  source: string;
  onLLMResult: (yamlText: string, configId: string) => void;
  loading?: boolean;
  loadError?: string | null;
  matches?: ConfigMatch[] | null;
  /** Show the YAML editor on first render (used when StageRulesPanel sends
   * the user here to edit a non-adapter section). */
  initialYamlMode?: boolean;
}

export default function AdapterPanel({
  config,
  onChange,
  configKey,
  setConfigKey,
  inputData,
  source,
  onLLMResult,
  loading,
  loadError,
  matches,
  initialYamlMode,
}: Props) {
  const [tab, setTab] = useState<Tab>("match");
  const [showYaml, setShowYaml] = useState(initialYamlMode === true);
  const [emitIdx, setEmitIdx] = useState(0);
  const [showLLM, setShowLLM] = useState(false);

  // YAML editor state — only meaningful while showYaml is true.
  const [yamlText, setYamlText] = useState<string>("");
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [savedYaml, setSavedYaml] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Re-seed the buffer from the current config every time we enter YAML mode
  // or the active config changes. The parsed config is the source of truth in
  // visual mode; flipping into YAML mode regenerates the on-disk shape.
  useEffect(() => {
    if (!showYaml || !config) return;
    const text = dumpAdapterYaml(config);
    setYamlText(text);
    setSavedYaml(text);
    setYamlError(null);
    setSaveError(null);
    setSavedAt(null);
    // We want this to fire on entering YAML mode or when the user picks a
    // different config — not on every visual edit (those are reflected via the
    // re-seed-on-toggle path).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showYaml, configKey]);

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
  const canSave = showYaml && !yamlError && dirty && !saving && config != null;

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

  return (
    <div>
      <div className="section-sub">Stage 02 · Tier-1 YAML adapter</div>
      <h2 className="section-title">Adapter</h2>
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
          <button className="btn" onClick={() => setShowYaml((s) => !s)}>
            {showYaml ? "Visual" : "YAML"}
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
                            {m.adapter.description}
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
            {showYaml ? (
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
                    className={cx("btn", canSave && "primary")}
                    disabled={!canSave}
                    onClick={handleSave}
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="tabs" style={{ flex: 1, border: "none" }}>
                <button
                  className={cx("tab", tab === "match" && "active")}
                  onClick={() => setTab("match")}
                >
                  match
                  <span className="badge">{config.match.record.length}</span>
                </button>
                <button
                  className={cx("tab", tab === "defaults" && "active")}
                  onClick={() => setTab("defaults")}
                >
                  defaults
                </button>
                <button
                  className={cx("tab", tab === "emit" && "active")}
                  onClick={() => setTab("emit")}
                >
                  emit
                  <span className="badge">{config.emit.length}</span>
                </button>
                <button
                  className={cx("tab", tab === "header" && "active")}
                  onClick={() => setTab("header")}
                >
                  adapter header
                </button>
              </div>
            )}
          </div>

          <div className="card-body">
            {showYaml ? (
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
            ) : (
              <>
                {tab === "header" && (
                  <div>
                    <div className="row">
                      <div className="field">
                        <label>id</label>
                        <input
                          className="input mono"
                          value={config.adapter.id}
                          onChange={(e) =>
                            onChange({
                              ...config,
                              adapter: { ...config.adapter, id: e.target.value },
                            })
                          }
                        />
                      </div>
                      <div className="field">
                        <label>version</label>
                        <input
                          className="input mono"
                          value={config.adapter.version}
                          onChange={(e) =>
                            onChange({
                              ...config,
                              adapter: { ...config.adapter, version: e.target.value },
                            })
                          }
                        />
                      </div>
                    </div>
                    <div className="spacer-sm" />
                    <div className="field">
                      <label>description</label>
                      <textarea
                        className="textarea"
                        rows={2}
                        value={config.adapter.description ?? ""}
                        onChange={(e) =>
                          onChange({
                            ...config,
                            adapter: { ...config.adapter, description: e.target.value },
                          })
                        }
                      />
                    </div>
                  </div>
                )}
                {tab === "match" && (
                  <MatchEditor
                    match={config.match}
                    onChange={(m) => onChange({ ...config, match: m })}
                  />
                )}
                {tab === "defaults" && (
                  <DefaultsEditor
                    defaults={config.defaults}
                    onChange={(d) => onChange({ ...config, defaults: d })}
                  />
                )}
                {tab === "emit" && (
                  <div>
                    <div
                      className="tabs"
                      style={{ marginBottom: 18, borderBottom: "1px solid var(--line)" }}
                    >
                      {config.emit.map((rule, i) => (
                        <button
                          key={rule.id}
                          className={cx("tab", emitIdx === i && "active")}
                          onClick={() => setEmitIdx(i)}
                        >
                          {rule.id}
                          {rule.iterate && <span className="badge">iter</span>}
                        </button>
                      ))}
                    </div>
                    <EmitEditor
                      emit={config.emit[emitIdx]}
                      onChange={(emit) => {
                        const arr = [...config.emit];
                        arr[emitIdx] = emit;
                        onChange({ ...config, emit: arr });
                      }}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
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

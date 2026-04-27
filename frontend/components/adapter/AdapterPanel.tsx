"use client";

import { useState } from "react";

import { cx } from "@/lib/cx";
import type { AdapterConfig } from "@/lib/types";

import YamlBlock from "../YamlBlock";
import DefaultsEditor from "./DefaultsEditor";
import EmitEditor from "./EmitEditor";
import LLMDialog from "./LLMDialog";
import MatchEditor from "./MatchEditor";

type Tab = "header" | "match" | "defaults" | "emit";

interface Props {
  config: AdapterConfig | null;
  onChange: (next: AdapterConfig) => void;
  configKey: string;
  setConfigKey: (k: string) => void;
  configIds: string[];
  inputData: unknown | null;
  source: string;
  onLLMResult: (yamlText: string, configId: string) => void;
  loading?: boolean;
  loadError?: string | null;
}

export default function AdapterPanel({
  config,
  onChange,
  configKey,
  setConfigKey,
  configIds,
  inputData,
  source,
  onLLMResult,
  loading,
  loadError,
}: Props) {
  const [tab, setTab] = useState<Tab>("match");
  const [showYaml, setShowYaml] = useState(false);
  const [emitIdx, setEmitIdx] = useState(0);
  const [showLLM, setShowLLM] = useState(false);

  return (
    <div>
      <div className="section-sub">Stage 02 · Tier-1 YAML adapter</div>
      <h2 className="section-title">Adapter</h2>
      <p className="muted" style={{ maxWidth: 700, marginTop: 0 }}>
        A config-driven adapter shapes raw records into{" "}
        <span className="mono">CanonicalEvent</span>s. No source-specific Python — every adapter is YAML.
        Pick an existing one, edit it visually, or generate a new config with an LLM from a record.
      </p>

      <div className="row" style={{ marginTop: 20, alignItems: "end" }}>
        <div className="field" style={{ flex: 2 }}>
          <label>Adapter config</label>
          <select
            className="select"
            value={configKey}
            onChange={(e) => setConfigKey(e.target.value)}
            disabled={configIds.length === 0}
          >
            {configIds.length === 0 && <option value="">No configs available</option>}
            {configIds.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          {loading && (
            <div className="help" style={{ marginTop: 4 }}>
              Loading…
            </div>
          )}
          {loadError && (
            <div className="help" style={{ color: "var(--err)" }}>
              {loadError}
            </div>
          )}
        </div>
        <div style={{ flex: 0, display: "flex", gap: 8 }}>
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
          </div>

          <div className="card-body">
            {showYaml ? (
              <YamlBlock
                data={
                  tab === "match"
                    ? { match: config.match }
                    : tab === "defaults"
                      ? { defaults: config.defaults }
                      : tab === "emit"
                        ? { emit: [config.emit[emitIdx]] }
                        : { adapter: config.adapter }
                }
              />
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

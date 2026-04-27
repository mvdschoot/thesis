"use client";

import { Fragment } from "react";

import type { Binding } from "@/lib/types";

interface Props {
  binding: Binding | undefined;
}

function pathToSegs(path: string): string[] {
  if (!path) return [];
  return String(path)
    .split(/(?=\.)|(?=\[)/)
    .map((s) => s.replace(/^\./, ""));
}

export default function PathPill({ binding }: Props) {
  if (binding === null || binding === undefined) {
    return (
      <span className="path-pill">
        <span className="lit">null</span>
      </span>
    );
  }
  if (typeof binding === "string") {
    return (
      <span className="path-pill">
        <span className="lit">&quot;{binding}&quot;</span>
      </span>
    );
  }
  if (typeof binding === "number" || typeof binding === "boolean") {
    return (
      <span className="path-pill">
        <span className="lit">{String(binding)}</span>
      </span>
    );
  }

  if ("template" in binding && binding.template) {
    return (
      <span className="path-pill" title="template">
        <span className="seg">tpl</span>
        <span className="arr">·</span>
        <span className="lit">&quot;{binding.template}&quot;</span>
      </span>
    );
  }

  if ("lookup" in binding && binding.lookup) {
    return (
      <span className="path-pill" title="lookup">
        <span className="seg">lookup</span>
        <span className="arr">·</span>
        <span className="seg">{String(binding.lookup)}</span>
      </span>
    );
  }

  if ("multiply" in binding && binding.multiply) {
    return (
      <span className="path-pill" title="multiply">
        <span className="seg">×</span>
      </span>
    );
  }

  if ("path" in binding && binding.path) {
    const segs = pathToSegs(binding.path);
    return (
      <span className="path-pill" title={binding.path}>
        {segs.map((s, i) => (
          <Fragment key={i}>
            {i > 0 && !s.startsWith("[") && <span className="arr">.</span>}
            <span className={s.startsWith("@") ? "item" : "seg"}>{s.replace(/^\./, "")}</span>
          </Fragment>
        ))}
        {binding.transform && <span className="tx">→ {binding.transform}</span>}
      </span>
    );
  }

  if ("date_from" in binding || "time_from" in binding) {
    return (
      <span className="path-pill" title="date+time compose">
        <span className="seg">date</span>
        {typeof binding.date_from === "object" &&
          binding.date_from &&
          "path" in binding.date_from && (
            <span className="lit"> {binding.date_from.path}</span>
          )}
        <span className="arr"> + </span>
        <span className="seg">time</span>
        {typeof binding.time_from === "object" &&
          binding.time_from &&
          "path" in binding.time_from && (
            <span className="lit"> {binding.time_from.path}</span>
          )}
      </span>
    );
  }

  return (
    <span className="path-pill">
      <span className="lit">{JSON.stringify(binding)}</span>
    </span>
  );
}

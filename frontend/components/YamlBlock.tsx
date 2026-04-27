"use client";

import { useMemo } from "react";

import { yamlify } from "@/lib/yaml";

interface Props {
  data: unknown;
}

export default function YamlBlock({ data }: Props) {
  const text = useMemo(() => yamlify(data).replace(/^\n/, ""), [data]);
  const lines = text.split("\n");

  return (
    <pre className="yaml-block">
      {lines.map((ln, i) => {
        const m = ln.match(/^(\s*)([^:\s][^:]*):(\s?)(.*)$/);
        if (m) {
          const valueClass =
            /^"/.test(m[4])
              ? "yaml-str"
              : /^-?\d/.test(m[4])
                ? "yaml-num"
                : /^null$/.test(m[4])
                  ? "yaml-null"
                  : "";
          return (
            <div key={i}>
              <span>{m[1]}</span>
              <span className="yaml-key">{m[2]}</span>
              <span>:{m[3]}</span>
              <span className={valueClass}>{m[4]}</span>
            </div>
          );
        }
        return <div key={i}>{ln}</div>;
      })}
    </pre>
  );
}

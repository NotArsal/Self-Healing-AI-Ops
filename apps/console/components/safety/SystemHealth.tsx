/**
 * The left zone: project identity and dependency health.
 *
 * Two Ollama rows, not one, and the distinction is the point: the target
 * reaches Ollama through Toxiproxy, Kavach reaches it directly and must keep
 * working when the target's path is broken (PRD.md §6.3). One merged row would
 * make an injected endpoint fault look like a broken diagnostician.
 *
 * Every row carries a word and an icon, never a colour alone (§10).
 */

import { Icon } from "../ui/Icon";
import { OkText } from "../ui/pills";
import type { System } from "@/lib/api";

export function SystemHealth({
  system,
  error,
}: {
  system: System | null;
  error: string;
}) {
  if (error) {
    return (
      <section aria-labelledby="health-heading" className="k-card">
        <h2 id="health-heading">System</h2>
        <p className="k-sm" style={{ margin: "8px 0 0", color: "var(--k-risk-high)" }}>
          {error}
        </p>
      </section>
    );
  }

  if (!system) {
    return (
      <section aria-labelledby="health-heading" className="k-card">
        <h2 id="health-heading">System</h2>
        <div
          aria-hidden="true"
          style={{
            marginTop: 8,
            height: 120,
            borderRadius: "var(--k-radius-sm)",
            background: "var(--k-surface-raised)",
          }}
        />
        <span className="k-sr-only">Loading system health.</span>
      </section>
    );
  }

  const healthy = system.dependencies.filter((d) => d.ok).length;

  return (
    <section
      aria-labelledby="health-heading"
      style={{ display: "flex", flexDirection: "column", gap: "var(--k-space-4)" }}
    >
      <div>
        <h2 id="health-heading">{system.project}</h2>
        <dl
          className="k-mono-sm"
          style={{
            margin: "var(--k-space-2) 0 0",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "2px var(--k-space-2)",
          }}
        >
          <dt className="k-faint">compose</dt>
          <dd style={{ margin: 0, overflowWrap: "anywhere" }}>
            {system.compose_project}
          </dd>
          <dt className="k-faint">threshold</dt>
          <dd style={{ margin: 0 }}>
            {system.rerank_threshold ?? "unknown"}
          </dd>
          <dt className="k-faint">config</dt>
          <dd style={{ margin: 0, overflowWrap: "anywhere" }}>
            {system.config_hash || "unknown"}
          </dd>
          <dt className="k-faint">corpus</dt>
          <dd style={{ margin: 0 }}>
            {system.corpus
              ? `${system.corpus.chunks ?? "?"} chunks / ${system.corpus.files ?? "?"} files`
              : "unknown"}
          </dd>
          <dt className="k-faint">kavach</dt>
          <dd style={{ margin: 0 }}>{system.kavach_version}</dd>
        </dl>
      </div>

      <div>
        <h3 style={{ marginBottom: "var(--k-space-2)" }}>
          Dependencies{" "}
          <span className="k-xs k-faint" style={{ fontWeight: 400 }}>
            {healthy}/{system.dependencies.length} ok
          </span>
        </h3>
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {system.dependencies.map((dependency) => (
            <li
              key={dependency.name}
              style={{
                padding: "6px 0",
                borderBottom: "1px solid var(--k-border-subtle)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: "var(--k-space-2)",
                }}
              >
                <span className="k-sm">{dependency.name}</span>
                <span className="k-xs">
                  <OkText ok={dependency.ok} okWord="ok" badWord="failing" />
                </span>
              </div>
              {(dependency.detail || dependency.endpoint) && (
                <p
                  className="k-mono-sm k-faint"
                  style={{ margin: "2px 0 0", overflowWrap: "anywhere" }}
                >
                  {dependency.endpoint}
                  {dependency.detail ? ` · ${dependency.detail}` : ""}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>

      <p
        className="k-xs"
        style={{
          margin: 0,
          display: "flex",
          gap: 6,
          color: "var(--k-text-faint)",
        }}
      >
        <Icon name="info" />
        <span>
          Mode {system.mode} is a configured value. It does not gate any action
          yet — the safety engine is not implemented, and the loop runs only when
          an operator starts it.
        </span>
      </p>
    </section>
  );
}

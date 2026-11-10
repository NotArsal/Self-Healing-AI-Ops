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

import { Sparkline } from "../charts/Sparkline";
import { Icon } from "../ui/Icon";
import { OkText } from "../ui/pills";
import type { FleetMetrics, System } from "@/lib/api";

/** A rate the backend reports as null has no data behind it. Rendering it as
 *  0 would claim "instant" where the truth is "never measured", which is the
 *  one number this project must not fabricate. */
function Readout({
  label,
  value,
  visual,
}: {
  label: string;
  value: string | null;
  visual?: React.ReactNode;
}) {
  return (
    <div
      style={{
        padding: "var(--k-space-2) var(--k-space-3)",
        background: "var(--k-surface-sunken)",
        border: "1px solid var(--k-border-subtle)",
        borderRadius: "var(--k-radius-sm)",
        display: "flex",
        flexDirection: "column",
        gap: 2,
      }}
    >
      <div className="k-mono-metric">{value ?? "—"}</div>
      <div className="k-xs k-faint">{label}</div>
      {visual && <div style={{ marginTop: 4 }}>{visual}</div>}
    </div>
  );
}

export function SystemHealth({
  system,
  error,
  metrics = null,
}: {
  system: System | null;
  error: string;
  metrics?: FleetMetrics | null;
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

      {metrics && (
        <div>
          <h3 style={{ marginBottom: "var(--k-space-2)" }}>Fleet</h3>
          {metrics.available ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "var(--k-space-2)",
              }}
            >
              <Readout
                label="MTTR"
                value={
                  metrics.mttr_seconds === null || metrics.mttr_seconds === undefined
                    ? null
                    : `${metrics.mttr_seconds}s`
                }
              />
              <Readout
                label="Repair success"
                value={
                  metrics.repair_success_rate === null ||
                  metrics.repair_success_rate === undefined
                    ? null
                    : `${Math.round(metrics.repair_success_rate * 100)}%`
                }
                visual={
                  metrics.repair_success_rate !== null &&
                  metrics.repair_success_rate !== undefined ? (
                    <Sparkline
                      type="bullet"
                      data={[Math.round(metrics.repair_success_rate * 100)]}
                      max={100}
                      label="Repair success rate"
                      unit="%"
                      height={5}
                      color="var(--k-risk-low)"
                    />
                  ) : undefined
                }
              />
              <Readout label="Auto-healed" value={String(metrics.auto_healed)} />
              <Readout label="Awaiting" value={String(metrics.awaiting)} />
            </div>
          ) : (
            <p className="k-sm k-muted" style={{ margin: 0 }}>
              No incident store, so there is nothing to average. MTTR and repair
              success need persisted history.
            </p>
          )}
        </div>
      )}

      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--k-space-2)",
            gap: "var(--k-space-2)",
          }}
        >
          <h3 style={{ margin: 0 }}>
            Dependencies{" "}
            <span className="k-xs k-faint" style={{ fontWeight: 400 }}>
              {healthy}/{system.dependencies.length} ok
            </span>
          </h3>
          {system.dependencies.length > 0 && (
            <Sparkline
              type="bullet"
              data={[healthy]}
              max={system.dependencies.length}
              label="Healthy dependencies ratio"
              color={healthy === system.dependencies.length ? "var(--k-risk-low)" : "var(--k-risk-med)"}
              width={64}
              height={6}
            />
          )}
        </div>
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
          {system.mode_is_enforced ? (
            <>
              Mode {system.mode} is enforced: every repair passes `permit()`
              before anything is written, and the deny-list is refused in every
              mode.
            </>
          ) : (
            <>
              Mode {system.mode} is a fallback, not this project&rsquo;s policy:
              the target manifest could not be read, so there is nothing to run
              under and every repair is refused. See the Safety policy row.
            </>
          )}
        </span>
      </p>
    </section>
  );
}

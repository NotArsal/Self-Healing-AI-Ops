/**
 * The observability screen — ADR 0018.
 *
 * Six sections, because those are the six things an operator asks about a
 * running control plane: alerts, service health, AI calls, exceptions, logs,
 * and traces.
 *
 * WHY THIS IS A SEPARATE ROUTE and not more panels on `/`:
 * the operations screen answers "what is happening to THIS incident, and do I
 * approve it". These answer "how is the control plane itself behaving". Mixing
 * them would put fleet-wide noise next to the approval dialog, which is the
 * one place in the product where a distracted human is expensive.
 *
 * NOTHING HERE IS A NEW MEASUREMENT. Every number is something the loop, the
 * gate or the log buffer already recorded and nobody could see. Traces and
 * metric history deliberately link out to Jaeger and Grafana rather than being
 * re-implemented: a worse copy of a trace viewer, inside the console, would be
 * a second thing to maintain and a second thing to be wrong.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { SystemHealth } from "@/components/safety/SystemHealth";
import { api, type Alert, type LlmCall, type LogLine } from "@/lib/api";
import { useSystem } from "@/lib/live";

const JAEGER_BASE =
  process.env.NEXT_PUBLIC_KAVACH_JAEGER ?? "http://localhost:16686";
const GRAFANA_BASE =
  process.env.NEXT_PUBLIC_KAVACH_GRAFANA ?? "http://localhost:3002";

/** Jaeger's own deep-link shape, filtered by the span attribute `telemetry.py`
 *  sets on every run. One incident, one trace, no searching. */
const traceUrl = (incidentId: string): string =>
  `${JAEGER_BASE}/search?service=kavach-control-plane` +
  `&tags=${encodeURIComponent(JSON.stringify({ "kavach.incident_id": incidentId }))}`;

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--k-state-escalated)",
  warning: "var(--k-risk-med)",
  info: "var(--k-text-muted)",
};

const LEVEL_COLOR: Record<string, string> = {
  critical: "var(--k-state-escalated)",
  error: "var(--k-state-escalated)",
  warning: "var(--k-risk-med)",
  info: "var(--k-text-muted)",
  debug: "var(--k-text-muted)",
};

function Section({
  title,
  hint,
  children,
  right,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: "var(--k-space-5)", maxWidth: 1040 }}>
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--k-space-3)",
          marginBottom: "var(--k-space-2)",
        }}
      >
        <h2 style={{ margin: 0 }}>{title}</h2>
        {right}
      </header>
      <p className="k-sm k-muted" style={{ margin: "0 0 var(--k-space-3)", maxWidth: "76ch" }}>
        {hint}
      </p>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="k-sm k-muted"
      style={{
        margin: 0,
        padding: "var(--k-space-3)",
        border: "1px dashed var(--k-border)",
        borderRadius: "var(--k-radius-sm)",
      }}
    >
      {children}
    </p>
  );
}

export default function ObservabilityPage() {
  const { system } = useSystem();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [calls, setCalls] = useState<LlmCall[]>([]);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [level, setLevel] = useState<"" | "warning">("");
  const [failed, setFailed] = useState("");

  const load = useCallback(async () => {
    const [a, c, l] = await Promise.all([
      api.GET("/v1/alerts"),
      api.GET("/v1/llm-calls", { params: { query: { limit: 50 } } }),
      api.GET("/v1/logs", { params: { query: { limit: 150 } } }),
    ]);
    if (a.error && c.error && l.error) {
      setFailed("Could not reach the control plane.");
      return;
    }
    setFailed("");
    setAlerts(a.data ?? []);
    setCalls(c.data ?? []);
    setLogs(l.data ?? []);
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 5000);
    return () => clearInterval(t);
  }, [load]);

  const shown = level === "warning"
    ? logs.filter((r) => ["warning", "error", "critical"].includes(r.level))
    : logs;
  const exceptions = logs.filter(
    (r) => r.exception || r.level === "error" || r.level === "critical",
  );

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current="/observability"
      />

      <main
        className="k-scroll"
        style={{ flex: 1, padding: "var(--k-space-5) var(--k-space-6)", minWidth: 0 }}
      >
        <header style={{ marginBottom: "var(--k-space-4)", maxWidth: 1040 }}>
          <h1>Observability</h1>
          <p className="k-sm k-muted" style={{ margin: "4px 0 0", maxWidth: "76ch" }}>
            Kavach watching itself. Everything here is read-only and nothing is a
            new measurement — these are figures the loop, the gate and the log
            buffer already recorded. Traces and metric history link out rather
            than being re-implemented.
          </p>
        </header>

        {failed && (
          <p className="k-sm" style={{ color: "var(--k-state-escalated)" }} role="alert">
            {failed}
          </p>
        )}

        {/* --- 1. alerts --- */}
        <Section
          title="Alerts"
          hint="Rules over Kavach's own state, most severe first. Every one reads a
                limit permit() itself enforces or an invariant the system claims, so
                each answers the same question: why will the next repair be refused?
                Displayed, never delivered — nothing here pages anyone."
        >
          {alerts.length === 0 ? (
            <Empty>Nothing is firing. The gate would permit a repair right now.</Empty>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--k-space-2)" }}>
              {alerts.map((a) => (
                <li
                  key={a.id}
                  style={{
                    padding: "var(--k-space-3)",
                    border: "1px solid var(--k-border)",
                    borderLeft: `2px solid ${SEVERITY_COLOR[a.severity]}`,
                    borderRadius: "var(--k-radius-sm)",
                    background: "var(--k-surface)",
                  }}
                >
                  <div style={{ display: "flex", gap: "var(--k-space-2)", alignItems: "center" }}>
                    <span className="k-mono k-sm" style={{ color: SEVERITY_COLOR[a.severity] }}>
                      {a.severity.toUpperCase()}
                    </span>
                    <strong>{a.title}</strong>
                  </div>
                  <p className="k-sm" style={{ margin: "6px 0 0" }}>{a.detail}</p>
                  {a.action && (
                    <p className="k-sm k-muted" style={{ margin: "4px 0 0" }}>→ {a.action}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* --- 2. service health --- */}
        <Section
          title="Service health"
          hint="Cheap probes only — no fast set and no LLM call, so this can be polled
                without costing tokens. Detection reads these same dependencies, so a
                red row here means a heal attempted now would be blind."
        >
          <SystemHealth system={system} error={failed} />
        </Section>

        {/* --- 3. AI calls --- */}
        <Section
          title="AI calls"
          hint="Every diagnosis the model produced, and what the deterministic validator
                did with it. The pair that matters is the fault class and the verdict:
                a confident diagnosis that was refused is the architecture working, not
                a failure. Raw generations are deliberately not shown."
        >
          {calls.length === 0 ? (
            <Empty>No LLM diagnosis yet. RCA runs only after deterministic detection finds a fault.</Empty>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="k-sm" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--k-text-muted)" }}>
                    <th style={{ padding: "6px 10px 6px 0" }}>Incident</th>
                    <th style={{ padding: "6px 10px" }}>Model</th>
                    <th style={{ padding: "6px 10px" }}>Latency</th>
                    <th style={{ padding: "6px 10px" }}>Tokens</th>
                    <th style={{ padding: "6px 10px" }}>Said</th>
                    <th style={{ padding: "6px 10px" }}>Confidence</th>
                    <th style={{ padding: "6px 10px" }}>Validator</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c) => (
                    <tr key={`${c.incident_id}-${c.at}`} style={{ borderTop: "1px solid var(--k-border)" }}>
                      <td className="k-mono" style={{ padding: "8px 10px 8px 0" }}>{c.incident_id}</td>
                      <td className="k-mono" style={{ padding: "8px 10px" }}>{c.model || "—"}</td>
                      <td style={{ padding: "8px 10px" }}>{c.latency_s ? `${c.latency_s.toFixed(1)}s` : "—"}</td>
                      <td style={{ padding: "8px 10px" }}>
                        {c.prompt_tokens || c.completion_tokens
                          ? `${c.prompt_tokens} / ${c.completion_tokens}`
                          : "—"}
                      </td>
                      <td className="k-mono" style={{ padding: "8px 10px" }}>
                        {c.error ? <span style={{ color: "var(--k-state-escalated)" }}>error</span> : (c.fault_class ?? "—")}
                      </td>
                      <td style={{ padding: "8px 10px" }} title="Not a calibrated probability">
                        {c.confidence == null ? "—" : `${c.confidence.toFixed(2)}*`}
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        {c.approved ? (
                          <span style={{ color: "var(--k-state-resolved)" }}>
                            <Icon name="check" size={12} /> {c.approved_action ?? "accepted"}
                          </span>
                        ) : (
                          <span
                            style={{ color: "var(--k-risk-med)" }}
                            title={(c.rejection_reasons ?? []).join("; ") || c.error}
                          >
                            <Icon name="ban" size={12} /> refused
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="k-sm k-muted" style={{ margin: "var(--k-space-2) 0 0" }}>
                * confidence is the model&apos;s own number and is not calibrated. It gates
                execution at 0.75; it is not a probability of being right.
              </p>
            </div>
          )}
        </Section>

        {/* --- 4. exceptions --- */}
        <Section
          title="Exceptions"
          hint="Errors and tracebacks from the control plane itself. Distinct from an
                escalated incident, which is Kavach deciding not to act — that is on the
                operations screen and is not a fault."
        >
          {exceptions.length === 0 ? (
            <Empty>No errors recorded since the control plane started.</Empty>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--k-space-2)" }}>
              {exceptions.slice(0, 20).map((r, i) => (
                <li
                  key={`${r.at}-${i}`}
                  style={{
                    padding: "var(--k-space-3)",
                    border: "1px solid var(--k-border)",
                    borderLeft: "2px solid var(--k-state-escalated)",
                    borderRadius: "var(--k-radius-sm)",
                  }}
                >
                  <div className="k-mono k-sm">
                    <span className="k-muted">{r.at}</span> {r.event}
                    {r.incident_id && <span className="k-muted"> · {r.incident_id}</span>}
                  </div>
                  {r.detail && <p className="k-sm k-muted" style={{ margin: "4px 0 0" }}>{r.detail}</p>}
                  {r.exception && (
                    <pre
                      className="k-mono k-sm k-scroll"
                      style={{ margin: "6px 0 0", maxHeight: 160, overflow: "auto" }}
                    >
                      {r.exception}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* --- 5. logs --- */}
        <Section
          title="Logs"
          hint="The control plane's own structured log, newest first. In-process and
                bounded, so a restart clears it — the durable record of what Kavach did
                is the hash-chained audit trail, not this. Keys that look like
                credentials are redacted before a line is ever stored."
          right={
            <button
              type="button"
              onClick={() => setLevel(level === "" ? "warning" : "")}
              className="k-sm"
              style={{
                padding: "4px 10px",
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border)",
                background: level === "warning" ? "var(--k-surface-raised)" : "transparent",
                color: "var(--k-text)",
              }}
            >
              {level === "warning" ? "Showing warnings and above" : "Showing everything"}
            </button>
          }
        >
          {shown.length === 0 ? (
            <Empty>
              Nothing logged yet. The control plane is deliberately quiet — there are four
              log statements in it, and the audit trail carries the decisions.
            </Empty>
          ) : (
            <div
              className="k-scroll"
              style={{
                maxHeight: 360,
                overflow: "auto",
                border: "1px solid var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
              }}
            >
              <table className="k-mono k-sm" style={{ width: "100%", borderCollapse: "collapse" }}>
                <tbody>
                  {shown.map((r, i) => (
                    <tr key={`${r.at}-${i}`} style={{ borderBottom: "1px solid var(--k-border)" }}>
                      <td className="k-muted" style={{ padding: "4px 10px", whiteSpace: "nowrap", verticalAlign: "top" }}>
                        {r.at.slice(11, 23) || r.at}
                      </td>
                      <td style={{ padding: "4px 10px", color: LEVEL_COLOR[r.level], verticalAlign: "top" }}>
                        {r.level}
                      </td>
                      <td style={{ padding: "4px 10px", verticalAlign: "top" }}>
                        {r.event}
                        {r.detail && <span className="k-muted"> {r.detail}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* --- 6. traces --- */}
        <Section
          title="Traces"
          hint="One span per loop run, with each stage as an event on its timeline.
                Jaeger renders them; re-implementing a trace viewer here would be a
                worse copy and a second thing to be wrong."
        >
          <div style={{ display: "flex", gap: "var(--k-space-2)", flexWrap: "wrap" }}>
            <a
              href={`${JAEGER_BASE}/search?service=kavach-control-plane&operation=kavach.heal`}
              target="_blank"
              rel="noreferrer"
              className="k-sm"
              style={{
                padding: "8px 12px",
                border: "1px solid var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
              }}
            >
              All heal traces in Jaeger →
            </a>
            <a
              href={`${GRAFANA_BASE}/d/kavach-overview`}
              target="_blank"
              rel="noreferrer"
              className="k-sm"
              style={{
                padding: "8px 12px",
                border: "1px solid var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
              }}
            >
              Metric history in Grafana →
            </a>
          </div>
          {calls.length > 0 && (
            <ul style={{ listStyle: "none", margin: "var(--k-space-3) 0 0", padding: 0, display: "grid", gap: 4 }}>
              {calls.slice(0, 8).map((c) => (
                <li key={`trace-${c.incident_id}`}>
                  <a
                    href={traceUrl(c.incident_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="k-mono k-sm"
                  >
                    {c.incident_id} →
                  </a>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </main>
    </div>
  );
}

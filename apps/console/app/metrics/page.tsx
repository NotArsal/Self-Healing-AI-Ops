/**
 * Metrics — how Kavach is doing overall (ADR 0029).
 *
 * Drawn in the console from Kavach's own data rather than embedded from
 * Grafana (owner decision 2026-11-13). Nothing here is a new measurement:
 * fleet figures come from the store, per-class figures are derived from the
 * stored incidents (`lib/stats.ts`), alerts and AI calls are the existing
 * endpoints. Grafana keeps the metric history over time.
 */

"use client";

import { SystemHealth } from "@/components/safety/SystemHealth";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Empty, Page, Section, Unreachable, UNREACHABLE } from "@/components/ui/Page";
import { sentence } from "@/components/ui/pills";
import { api } from "@/lib/api";
import { faultName } from "@/lib/faults";
import { usePolled, useSystem } from "@/lib/live";
import { byFaultClass, median } from "@/lib/stats";

const GRAFANA_BASE = process.env.NEXT_PUBLIC_KAVACH_GRAFANA ?? "http://localhost:3002";

const SEVERITY: Record<string, { colour: string; icon: IconName }> = {
  critical: { colour: "var(--k-state-escalated)", icon: "shield-x" },
  warning: { colour: "var(--k-risk-med)", icon: "shield-alert" },
  info: { colour: "var(--k-text-muted)", icon: "info" },
};

const loadFleet = () => api.GET("/v1/metrics");
const loadIncidents = () => api.GET("/v1/incidents", { params: { query: { limit: 1000 } } });
const loadAlerts = () => api.GET("/v1/alerts");
const loadCalls = () => api.GET("/v1/llm-calls", { params: { query: { limit: 200 } } });

/** A reading, not an object: no border (§7.11). */
function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="k-mono-metric">{value}</div>
      <div className="k-xs k-faint">{label}</div>
    </div>
  );
}

const secs = (s: number | null | undefined): string =>
  s === null || s === undefined ? "—" : `${s.toFixed(1)}s`;

const TH = { padding: "6px 10px 6px 0", fontWeight: 500 } as const;
const TD = { padding: "8px 10px 8px 0" } as const;

export default function MetricsPage() {
  const { system, error } = useSystem();
  const fleet = usePolled(loadFleet, 10_000);
  const incidents = usePolled(loadIncidents, 30_000);
  const alerts = usePolled(loadAlerts, 10_000);
  const calls = usePolled(loadCalls, 30_000);

  const f = fleet.data;
  const classes = byFaultClass(incidents.data ?? []);
  const llm = calls.data ?? [];
  const refused = llm.filter((c) => !c.approved).length;
  const latency = median(llm.map((c) => c.latency_s).filter((s) => s > 0));
  const tokens = llm.reduce((sum, c) => sum + c.prompt_tokens + c.completion_tokens, 0);

  return (
    <Page
      system={system}
      current="/metrics"
      title="Metrics"
      intro="How Kavach is doing across every stored incident: outcomes, time to repair by fault class, what the gate would refuse right now, and what the model costs."
    >
      <Unreachable message={fleet.failed && incidents.failed ? UNREACHABLE : ""} />

      <Section
        title="Fleet"
        hint="Repair success counts only repairs that ran: a run that escalated before writing anything is not a failed repair. MTTR is the mean over resolved incidents."
      >
        {!f ? (
          <Empty>Loading the fleet figures.</Empty>
        ) : !f.available ? (
          <Empty>No incident store, so there is nothing to count. These need persisted history.</Empty>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: "var(--k-space-4)",
            }}
          >
            <Readout label="Incidents" value={String(f.incidents)} />
            <Readout label="Healed" value={String(f.resolved)} />
            <Readout label="Escalated" value={String(f.escalated)} />
            <Readout label="Awaiting approval" value={String(f.awaiting)} />
            <Readout
              label="Repair success"
              value={
                f.repair_success_rate === null || f.repair_success_rate === undefined
                  ? "—"
                  : `${Math.round(f.repair_success_rate * 100)}%`
              }
            />
            <Readout label="MTTR" value={secs(f.mttr_seconds)} />
          </div>
        )}
      </Section>

      <Section
        title="By fault class"
        hint="From the stored incidents. An approved heal is two rows: the plan a person approved, and the run that fixed it, counted under healed. Median MTTR is over healed incidents, from that run's own detection to its resolution."
        right={
          <a href={`${GRAFANA_BASE}/d/kavach-overview`} target="_blank" rel="noreferrer" className="k-sm">
            History over time in Grafana
          </a>
        }
      >
        {classes.length === 0 ? (
          <Empty>No incidents yet.</Empty>
        ) : (
          <table className="k-sm" style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <caption className="k-sr-only">Incidents and outcomes per fault class.</caption>
            <thead>
              <tr className="k-xs k-faint">
                <th scope="col" style={TH}>Class</th>
                <th scope="col" style={TH}>Fault</th>
                <th scope="col" style={TH}>Incidents</th>
                <th scope="col" style={TH}>Healed</th>
                <th scope="col" style={TH}>Approved</th>
                <th scope="col" style={TH}>Escalated</th>
                <th scope="col" style={TH}>Median MTTR</th>
              </tr>
            </thead>
            <tbody className="k-num">
              {classes.map((c) => (
                <tr key={c.faultClass} style={{ borderTop: "1px solid var(--k-border-subtle)" }}>
                  <td className="k-mono" style={TD}>{c.faultClass}</td>
                  <td style={TD}>{c.faultClass === "none" ? "No fault class" : faultName(c.faultClass)}</td>
                  <td style={TD}>{c.incidents}</td>
                  <td style={TD}>{c.resolved}</td>
                  <td style={TD}>{c.approved}</td>
                  <td style={TD}>{c.escalated}</td>
                  <td className="k-mono" style={TD}>{secs(c.medianMttrS)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section
        title="Alerts"
        hint="Rules over Kavach's own state, most severe first. Each answers one question: why would the next repair be refused? Displayed here, never sent anywhere."
      >
        {(alerts.data ?? []).length === 0 ? (
          <Empty>Nothing is firing. The gate would permit a repair right now.</Empty>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--k-space-2)" }}>
            {(alerts.data ?? []).map((a) => {
              const look = SEVERITY[a.severity] ?? SEVERITY.info!;
              return (
                <li
                  key={a.id}
                  style={{
                    padding: "var(--k-space-3)",
                    border: "1px solid var(--k-border)",
                    borderLeft: `2px solid ${look.colour}`,
                    borderRadius: "var(--k-radius-sm)",
                    background: "var(--k-surface)",
                  }}
                >
                  <div style={{ display: "flex", gap: "var(--k-space-2)", alignItems: "center" }}>
                    {/* Icon and word, never colour alone (§10); sentence case (§3.2). */}
                    <span className="k-sm" style={{ color: look.colour, display: "inline-flex", gap: 6, alignItems: "center" }}>
                      <Icon name={look.icon} />
                      {sentence(a.severity)}
                    </span>
                    <strong>{a.title}</strong>
                  </div>
                  <p className="k-sm" style={{ margin: "6px 0 0" }}>{a.detail}</p>
                  {a.action && (
                    <p className="k-sm k-muted" style={{ margin: "4px 0 0" }}>Fix: {a.action}</p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section
        title="AI calls"
        hint="Every diagnosis the model produced and what the deterministic validator did with it. A confident diagnosis that was refused is the architecture working. Raw generations are not shown."
      >
        {llm.length === 0 ? (
          <Empty>No LLM diagnosis yet. RCA runs only after detection finds a fault.</Empty>
        ) : (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: "var(--k-space-4)",
                marginBottom: "var(--k-space-4)",
              }}
            >
              <Readout label="Diagnoses" value={String(llm.length)} />
              <Readout label="Refused by validator" value={String(refused)} />
              <Readout label="Median latency" value={secs(latency)} />
              <Readout label="Tokens, all calls" value={tokens.toLocaleString("en-GB")} />
            </div>
            <div className="k-scroll" style={{ maxHeight: 420, overflowX: "auto" }}>
              <table className="k-sm" style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <caption className="k-sr-only">LLM diagnoses, newest first.</caption>
                <thead>
                  <tr className="k-xs k-faint">
                    <th scope="col" style={TH}>Incident</th>
                    <th scope="col" style={TH}>Model</th>
                    <th scope="col" style={TH}>Latency</th>
                    <th scope="col" style={TH}>Tokens in / out</th>
                    <th scope="col" style={TH}>Said</th>
                    <th scope="col" style={TH}>Confidence</th>
                    <th scope="col" style={TH}>Validator</th>
                  </tr>
                </thead>
                <tbody className="k-num">
                  {llm.map((c) => (
                    <tr key={`${c.incident_id}-${c.at}`} style={{ borderTop: "1px solid var(--k-border-subtle)" }}>
                      <td className="k-mono" style={TD}>{c.incident_id}</td>
                      <td className="k-mono" style={TD}>{c.model || "—"}</td>
                      <td style={TD}>{c.latency_s ? `${c.latency_s.toFixed(1)}s` : "—"}</td>
                      <td style={TD}>
                        {c.prompt_tokens || c.completion_tokens
                          ? `${c.prompt_tokens} / ${c.completion_tokens}`
                          : "—"}
                      </td>
                      <td className="k-mono" style={TD}>
                        {c.error ? (
                          <span style={{ color: "var(--k-state-escalated)" }}>error</span>
                        ) : (
                          (c.fault_class ?? "—")
                        )}
                      </td>
                      <td style={TD} title="The model's own number, not calibrated">
                        {c.confidence == null ? "—" : `${c.confidence.toFixed(2)}*`}
                      </td>
                      <td style={TD}>
                        {c.approved ? (
                          <span style={{ color: "var(--k-state-resolved)", display: "inline-flex", gap: 6, alignItems: "center" }}>
                            <Icon name="check" /> {c.approved_action ?? "accepted"}
                          </span>
                        ) : (
                          <span
                            style={{ color: "var(--k-risk-med)", display: "inline-flex", gap: 6, alignItems: "center" }}
                            title={(c.rejection_reasons ?? []).join("; ") || c.error}
                          >
                            <Icon name="ban" /> refused
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="k-xs k-faint" style={{ margin: "var(--k-space-2) 0 0" }}>
              * The model&apos;s own confidence, not calibrated. It must clear 0.75 to be
              acted on; it is not a probability of being right.
            </p>
          </>
        )}
      </Section>

      <Section
        title="Service health"
        hint="Cheap probes only, no fast set and no LLM call. Detection reads these same dependencies, so a failing row means a heal started now would be blind."
      >
        <SystemHealth system={system} error={error} />
      </Section>
    </Page>
  );
}

/**
 * Traces — where one run spent its time (ADR 0029).
 *
 * Drawn from the run's stored timeline events (`lib/stats.ts`), so it works
 * offline and after a restart. Jaeger keeps the full span tree and is one
 * link away for each run; this page does not re-implement it.
 */

"use client";

import { useState } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { Empty, Page, Section, Unreachable, UNREACHABLE } from "@/components/ui/Page";
import { StatePill } from "@/components/ui/pills";
import { api } from "@/lib/api";
import { BAR_CELLS, bar } from "@/lib/ascii";
import { faultName } from "@/lib/faults";
import { usePolled, useStoredEvents, useSystem } from "@/lib/live";
import { runSeconds, stageTimings } from "@/lib/stats";

const JAEGER_BASE = process.env.NEXT_PUBLIC_KAVACH_JAEGER ?? "http://localhost:16686";

/** Jaeger's own deep link, by the span attribute `telemetry.py` sets. */
const traceUrl = (incidentId: string): string =>
  `${JAEGER_BASE}/search?service=kavach-control-plane` +
  `&tags=${encodeURIComponent(JSON.stringify({ "kavach.incident_id": incidentId }))}`;

const RESULT: Record<string, { icon: IconName; colour: string }> = {
  ok: { icon: "check", colour: "var(--k-risk-low)" },
  failed: { icon: "cross", colour: "var(--k-risk-high)" },
  info: { icon: "info", colour: "var(--k-text-muted)" },
  started: { icon: "pending", colour: "var(--k-text-muted)" },
};

const loadRuns = () => api.GET("/v1/incidents", { params: { query: { limit: 100 } } });

const TH = { padding: "6px 10px 6px 0", fontWeight: 500 } as const;
const TD = { padding: "6px 10px 6px 0", verticalAlign: "top" } as const;

export default function TracesPage() {
  const { system } = useSystem();
  const runs = usePolled(loadRuns, 30_000);
  const [picked, setPicked] = useState("");
  const id = picked || runs.data?.[0]?.incident_id || "";
  const events = useStoredEvents(id);
  const stages = stageTimings(events);
  const total = runSeconds(events);

  return (
    <Page
      system={system}
      current="/traces"
      title="Traces"
      intro="Where a run spent its time, stage by stage, from its stored timeline. Each run's full span tree is in Jaeger."
    >
      <Unreachable message={runs.failed ? UNREACHABLE : ""} />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
          gap: "var(--k-space-5)",
          alignItems: "start",
          maxWidth: 1200,
        }}
      >
        <Section title="Runs" hint="Newest first. Pick one to see its stages.">
          {(runs.data ?? []).length === 0 ? (
            <Empty>No runs yet. Start one from the operations screen.</Empty>
          ) : (
            <ul
              className="k-scroll"
              style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: "calc(100vh - 260px)" }}
            >
              {(runs.data ?? []).map((r) => {
                const active = r.incident_id === id;
                return (
                  <li key={r.incident_id}>
                    <button
                      type="button"
                      onClick={() => setPicked(r.incident_id)}
                      aria-current={active ? "true" : undefined}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr auto",
                        gap: "var(--k-space-2)",
                        alignItems: "center",
                        width: "100%",
                        minHeight: 48,
                        padding: "var(--k-space-2) var(--k-space-3)",
                        marginBottom: "var(--k-space-1)",
                        textAlign: "left",
                        background: active ? "var(--k-surface-raised)" : "var(--k-surface)",
                        border: `1px solid ${active ? "var(--k-border-strong)" : "var(--k-border)"}`,
                        borderRadius: "var(--k-radius-md)",
                      }}
                    >
                      <span style={{ minWidth: 0 }}>
                        <span className="k-sm" style={{ display: "block" }}>
                          {r.fault_class
                            ? `${r.fault_class} ${faultName(r.fault_class, r.fault_name)}`
                            : "No fault class"}
                        </span>
                        <span className="k-mono-sm k-faint">{r.incident_id}</span>
                      </span>
                      <StatePill status={r.status} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>

        <Section
          title={id ? `Stages of ${id}` : "Stages"}
          hint="Each stage runs from its first line to its last, so a stage that logged one line shows 0s. The bars scale to the whole run."
          right={
            id ? (
              <a href={traceUrl(id)} target="_blank" rel="noreferrer" className="k-sm">
                Open in Jaeger
              </a>
            ) : undefined
          }
        >
          {stages.length === 0 ? (
            <Empty>
              No stored events for this run. Events are stored since 2026-11-13, so an
              older run has only its Jaeger trace.
            </Empty>
          ) : (
            <>
              <table className="k-sm" style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <caption className="k-sr-only">Each stage of the run, its start, length and result.</caption>
                <thead>
                  <tr className="k-xs k-faint">
                    <th scope="col" style={TH}>Stage</th>
                    <th scope="col" style={TH}>Starts at</th>
                    <th scope="col" style={TH}>Took</th>
                    <th scope="col" style={TH}>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {stages.map((s) => {
                    const look = RESULT[s.status] ?? RESULT.info!;
                    return (
                      <tr key={s.stage} style={{ borderTop: "1px solid var(--k-border-subtle)" }}>
                        <td className="k-mono" style={TD}>{s.stage}</td>
                        <td className="k-mono-sm k-num" style={TD}>+{s.offsetS.toFixed(1)}s</td>
                        <td className="k-mono-sm k-num" style={{ ...TD, whiteSpace: "nowrap" }}>
                          {/* Data-bound ASCII (§7.12 B): the number beside it is the fact. */}
                          <span aria-hidden="true" className="k-muted">
                            {bar(s.tookS, total ?? 0)}
                          </span>{" "}
                          {s.tookS.toFixed(1)}s
                        </td>
                        <td style={TD}>
                          <span style={{ color: look.colour, display: "inline-flex", gap: 6, alignItems: "center" }}>
                            <Icon name={look.icon} />
                            {s.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {total !== null && total > 0 && (
                <p className="k-xs k-faint" style={{ margin: "var(--k-space-2) 0 0" }}>
                  Whole run {total.toFixed(1)}s. One cell is {(total / BAR_CELLS).toFixed(1)}s.
                </p>
              )}
            </>
          )}
        </Section>
      </div>
    </Page>
  );
}

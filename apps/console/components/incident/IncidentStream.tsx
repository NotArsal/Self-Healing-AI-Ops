/**
 * The incident stream and the history table — DESIGN_SYSTEM.md §7.3, §7.10.
 *
 * A real `<ul>` of `<li>`, not a div soup (§10). The selected row gets
 * `--k-border-strong` and a 2px left bar in its state colour, which is a
 * second, non-colour cue on top of `aria-current`.
 *
 * History is in-memory for P4: `Incident` is a dataclass and there is no
 * database yet, so restarting the control plane empties this. That is the
 * scope the phase was given, not an oversight.
 */

"use client";

import { LoopRing, ringStage } from "./LoopRing";
import { StatePill } from "../ui/pills";
import type { IncidentSummary, LoopEvent } from "@/lib/api";
import { type LoopStage } from "@/lib/tokens";
import { stateVar } from "@/lib/tokens";

const duration = (from: string, to: string): string => {
  if (!from) return "";
  const start = new Date(from).getTime();
  const end = to ? new Date(to).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m${String(seconds % 60).padStart(2, "0")}s`;
};

export function reachedStages(
  events: LoopEvent[],
  incidentId: string,
): { reached: Set<LoopStage>; failed: Set<LoopStage>; inFlight: boolean } {
  const reached = new Set<LoopStage>();
  const failed = new Set<LoopStage>();
  let inFlight = false;
  for (const event of events) {
    if (incidentId && event.incident_id && event.incident_id !== incidentId) continue;
    const stage = ringStage(event.stage);
    if (!stage) continue;
    reached.add(stage);
    if (event.status === "failed") failed.add(stage);
    // Every stage emits `started` and then `ok` or `failed`, so a stage is in
    // flight exactly when the newest event is a `started`. Latching this on a
    // `started` and only clearing it at `resolve` made the ring rotate from the
    // first event to the last, which would have been a spinner pretending to be
    // progress.
    inFlight = event.status === "started" && event.stage !== "resolve";
  }
  return { reached, failed, inFlight };
}

export function IncidentStream({
  incidents,
  selectedId,
  onSelect,
  events,
}: {
  incidents: IncidentSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  events: LoopEvent[];
}) {
  return (
    <section aria-labelledby="stream-heading">
      <h2 id="stream-heading" style={{ marginBottom: "var(--k-space-3)" }}>
        Incidents
      </h2>

      {incidents.length === 0 ? (
        <p className="k-sm k-muted" style={{ margin: 0 }}>
          No incidents. Kavach is watching one project and has run no loop yet.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {incidents.map((incident) => {
            const selected = incident.incident_id === selectedId;
            const { reached, failed, inFlight } = reachedStages(
              events,
              incident.incident_id,
            );
            return (
              <li key={incident.incident_id}>
                <button
                  type="button"
                  onClick={() => onSelect(incident.incident_id)}
                  aria-current={selected ? "true" : undefined}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "20px 1fr auto auto",
                    gap: "var(--k-space-3)",
                    alignItems: "center",
                    width: "100%",
                    minHeight: 64,
                    padding: "var(--k-space-2) var(--k-space-3)",
                    textAlign: "left",
                    background: selected
                      ? "var(--k-surface-raised)"
                      : "var(--k-surface)",
                    border: `1px solid ${selected ? "var(--k-border-strong)" : "var(--k-border)"}`,
                    borderLeft: `2px solid ${selected ? stateVar(incident.status) : "transparent"}`,
                    borderRadius: "var(--k-radius-md)",
                    marginBottom: "var(--k-space-2)",
                    transition: "background var(--k-dur-fast) var(--k-ease)",
                  }}
                >
                  <LoopRing
                    reached={reached}
                    failed={failed}
                    inFlight={inFlight}
                    size={20}
                  />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block", fontWeight: 500 }}>
                      {incident.fault_class
                        ? `${incident.fault_class} ${(incident.fault_name ?? "").replace(/_/g, " ")}`
                        : "No fault class"}
                    </span>
                    <span className="k-mono-sm k-faint">
                      {incident.incident_id}
                      {incident.service ? ` · ${incident.service}` : ""}
                      {incident.diagnosed_by ? ` · ${incident.diagnosed_by}` : ""}
                    </span>
                  </span>
                  <StatePill status={incident.status} />
                  <span className="k-mono-sm k-faint">
                    {duration(incident.detected_at, incident.resolved_at)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function HistoryTable({ incidents }: { incidents: IncidentSummary[] }) {
  if (incidents.length === 0) return null;
  return (
    <section aria-labelledby="history-heading" style={{ marginTop: "var(--k-space-5)" }}>
      <h2 id="history-heading" style={{ marginBottom: "var(--k-space-3)" }}>
        History
      </h2>
      <table
        className="k-sm"
        style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}
      >
        <caption className="k-sr-only">
          Every incident this control-plane process has run, newest first.
        </caption>
        <thead>
          <tr className="k-xs k-faint">
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Incident
            </th>
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Fault
            </th>
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Service
            </th>
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Detected
            </th>
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Status
            </th>
            <th scope="col" style={{ padding: "6px 8px", fontWeight: 500 }}>
              Outcome
            </th>
          </tr>
        </thead>
        <tbody className="k-mono-sm">
          {incidents.map((incident) => (
            <tr
              key={incident.incident_id}
              style={{ borderTop: "1px solid var(--k-border-subtle)" }}
            >
              <td style={{ padding: "6px 8px" }}>{incident.incident_id}</td>
              <td style={{ padding: "6px 8px" }}>{incident.fault_class ?? "—"}</td>
              <td style={{ padding: "6px 8px" }}>{incident.service ?? "—"}</td>
              <td style={{ padding: "6px 8px" }}>
                {incident.detected_at.slice(11, 19) || "—"}
              </td>
              <td style={{ padding: "6px 8px" }}>
                <StatePill status={incident.status} />
              </td>
              <td
                className="k-sm k-muted"
                style={{ padding: "6px 8px", fontFamily: "var(--k-font-sans)" }}
              >
                {incident.outcome || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

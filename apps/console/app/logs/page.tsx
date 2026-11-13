/**
 * Logs — the control plane's own log and its errors (ADR 0029).
 *
 * Moved from the observability page, unchanged in what it reads. In-process
 * and bounded: a restart clears it. The durable record of what Kavach did is
 * the hash-chained audit trail, not this.
 */

"use client";

import { useState } from "react";

import { Empty, Page, Section, Unreachable, UNREACHABLE } from "@/components/ui/Page";
import { api, type LogLine } from "@/lib/api";
import { usePolled, useSystem } from "@/lib/live";

const LEVEL_COLOR: Record<string, string> = {
  critical: "var(--k-state-escalated)",
  error: "var(--k-state-escalated)",
  warning: "var(--k-risk-med)",
  info: "var(--k-text-muted)",
  debug: "var(--k-text-muted)",
};

const loadLogs = () => api.GET("/v1/logs", { params: { query: { limit: 300 } } });

export default function LogsPage() {
  const { system } = useSystem();
  const { data, failed } = usePolled(loadLogs, 5_000);
  const [warningsOnly, setWarningsOnly] = useState(false);

  const logs: LogLine[] = data ?? [];
  const shown = warningsOnly
    ? logs.filter((r) => ["warning", "error", "critical"].includes(r.level))
    : logs;
  const exceptions = logs.filter(
    (r) => r.exception || r.level === "error" || r.level === "critical",
  );

  return (
    <Page
      system={system}
      current="/logs"
      title="Logs"
      intro="The control plane's own structured log, newest first, and the errors in it. A restart clears both; the audit trail is the durable record of what Kavach did."
    >
      <Unreachable message={failed ? UNREACHABLE : ""} />

      <Section
        title="Errors"
        hint="Errors and tracebacks from the control plane itself. Not the same as an escalated incident, which is Kavach deciding not to act."
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

      <Section
        title="Log"
        hint="Keys that look like credentials are redacted before a line is stored."
        right={
          <button
            type="button"
            onClick={() => setWarningsOnly((on) => !on)}
            aria-pressed={warningsOnly}
            className="k-sm"
            style={{
              minHeight: 40,
              padding: "0 var(--k-space-3)",
              borderRadius: "var(--k-radius-sm)",
              border: "1px solid var(--k-border)",
              background: warningsOnly ? "var(--k-surface-raised)" : "transparent",
              color: "var(--k-text)",
            }}
          >
            {warningsOnly ? "Showing warnings and above" : "Showing everything"}
          </button>
        }
      >
        {shown.length === 0 ? (
          <Empty>
            Nothing logged yet. The control plane is deliberately quiet, and the
            audit trail carries the decisions.
          </Empty>
        ) : (
          <div
            className="k-scroll"
            style={{
              maxHeight: 520,
              border: "1px solid var(--k-border)",
              borderRadius: "var(--k-radius-sm)",
            }}
          >
            <table className="k-mono k-sm" style={{ width: "100%", borderCollapse: "collapse" }}>
              <caption className="k-sr-only">Control-plane log lines, newest first.</caption>
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
                      {r.incident_id && <span className="k-muted"> · {r.incident_id}</span>}
                      {r.detail && <span className="k-muted"> {r.detail}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </Page>
  );
}

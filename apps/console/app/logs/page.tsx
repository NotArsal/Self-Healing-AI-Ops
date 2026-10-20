/**
 * The dedicated Logs screen — Phase 9.4.
 *
 * Provides a first-class, structured log viewer for the control plane.
 * Real log lines with timestamps, level, source logger, event, detail,
 * incident reference, and structured tracebacks.
 *
 * Integrates directly with GET /v1/logs.
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { api, type LogLine } from "@/lib/api";
import { useSystem } from "@/lib/live";

const LEVEL_COLOR: Record<string, string> = {
  critical: "var(--k-state-escalated)",
  error: "var(--k-state-escalated)",
  warning: "var(--k-risk-med)",
  info: "var(--k-text-muted)",
  debug: "var(--k-text-faint)",
};

const LEVEL_BG: Record<string, string> = {
  critical: "var(--k-risk-high-bg)",
  error: "var(--k-risk-high-bg)",
  warning: "var(--k-risk-med-bg)",
  info: "var(--k-surface-raised)",
  debug: "var(--k-surface-sunken)",
};

export default function LogsPage() {
  const { system } = useSystem();
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState("");

  // Filters
  const [search, setSearch] = useState("");
  const [selectedLevel, setSelectedLevel] = useState<string>("all");
  const [selectedLogger, setSelectedLogger] = useState<string>("all");

  const load = useCallback(async () => {
    setLoading(true);
    // When level is warning or error, query with level floor for efficient retrieval
    const queryLevel =
      selectedLevel === "warning" || selectedLevel === "error"
        ? selectedLevel
        : undefined;

    const { data, error } = await api.GET("/v1/logs", {
      params: { query: { level: queryLevel, limit: 500 } },
    });
    setLoading(false);
    if (error || !data) {
      setFailed("Could not fetch logs from control plane. Is the API up?");
      return;
    }
    setFailed("");
    setLogs(data);
  }, [selectedLevel]);

  useEffect(() => {
    void load();
  }, [load]);

  // Unique loggers extracted from real data
  const availableLoggers = useMemo(() => {
    const set = new Set<string>();
    for (const l of logs) {
      if (l.logger) set.add(l.logger);
    }
    return Array.from(set).sort();
  }, [logs]);

  // Filtered log lines
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return logs.filter((r) => {
      // Level filter
      if (selectedLevel === "error") {
        if (r.level !== "error" && r.level !== "critical") return false;
      } else if (selectedLevel === "warning") {
        if (r.level !== "warning" && r.level !== "error" && r.level !== "critical") return false;
      } else if (selectedLevel === "info") {
        if (r.level !== "info" && r.level !== "warning" && r.level !== "error" && r.level !== "critical") return false;
      }

      // Logger filter
      if (selectedLogger !== "all" && r.logger !== selectedLogger) return false;

      // Text query
      if (q) {
        const matchesEvent = r.event?.toLowerCase().includes(q);
        const matchesDetail = r.detail?.toLowerCase().includes(q);
        const matchesLogger = r.logger?.toLowerCase().includes(q);
        const matchesIncident = r.incident_id?.toLowerCase().includes(q);
        const matchesException = r.exception?.toLowerCase().includes(q);
        if (!matchesEvent && !matchesDetail && !matchesLogger && !matchesIncident && !matchesException) {
          return false;
        }
      }
      return true;
    });
  }, [logs, selectedLevel, selectedLogger, search]);

  const errorCount = logs.filter((l) => l.level === "error" || l.level === "critical").length;
  const warningCount = logs.filter((l) => l.level === "warning").length;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current="/logs"
      />

      <main
        className="k-scroll"
        style={{
          flex: 1,
          padding: "var(--k-space-4) var(--k-space-5)",
          overflowY: "auto",
        }}
      >
        {/* Page Header */}
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "var(--k-space-3)",
            marginBottom: "var(--k-space-4)",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 28,
                  height: 28,
                  borderRadius: "var(--k-radius-sm)",
                  background: "var(--k-accent-glow)",
                  color: "var(--k-accent)",
                }}
              >
                <Icon name="terminal" size={16} />
              </span>
              <h1 style={{ margin: 0 }}>Logs</h1>
              <span
                className="k-mono-sm"
                style={{
                  padding: "2px 8px",
                  borderRadius: "var(--k-radius-sm)",
                  background: "var(--k-surface-raised)",
                  border: "1px solid var(--k-border)",
                  color: "var(--k-text-muted)",
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {filtered.length} of {logs.length} lines
              </span>
            </div>
            <p className="k-sm k-muted" style={{ margin: "4px 0 0", maxWidth: "80ch" }}>
              The control plane&apos;s structured log stream, newest first. In-process and
              bounded: a restart clears it, while durable remediation records reside in the
              hash-chained audit ledger. Sensitive credentials are redacted at the logging layer.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="k-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 12px",
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border)",
                background: "var(--k-surface-raised)",
                color: "var(--k-text)",
                cursor: loading ? "default" : "pointer",
              }}
            >
              <Icon name="activity" size={13} />
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </header>

        {/* KPI Summary Tiles */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: "var(--k-space-2)",
            marginBottom: "var(--k-space-4)",
          }}
        >
          <div className="k-card" style={{ padding: "var(--k-space-3)" }}>
            <span className="k-xs k-faint">Total Buffered Lines</span>
            <div className="k-mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>
              {logs.length}
            </div>
          </div>
          <div className="k-card" style={{ padding: "var(--k-space-3)" }}>
            <span className="k-xs k-faint">Errors & Exceptions</span>
            <div
              className="k-mono"
              style={{
                fontSize: 20,
                fontWeight: 700,
                marginTop: 2,
                color: errorCount > 0 ? "var(--k-risk-high)" : "var(--k-risk-low)",
              }}
            >
              {errorCount}
            </div>
          </div>
          <div className="k-card" style={{ padding: "var(--k-space-3)" }}>
            <span className="k-xs k-faint">Warnings</span>
            <div
              className="k-mono"
              style={{
                fontSize: 20,
                fontWeight: 700,
                marginTop: 2,
                color: warningCount > 0 ? "var(--k-risk-med)" : "var(--k-text-muted)",
              }}
            >
              {warningCount}
            </div>
          </div>
          <div className="k-card" style={{ padding: "var(--k-space-3)" }}>
            <span className="k-xs k-faint">Active Subsystems</span>
            <div className="k-mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>
              {availableLoggers.length || "—"}
            </div>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <section
          aria-label="Log stream filters"
          style={{
            padding: "var(--k-space-3)",
            background: "var(--k-surface-sunken)",
            borderRadius: "var(--k-radius-sm)",
            border: "1px solid var(--k-border)",
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--k-space-3)",
            alignItems: "center",
            marginBottom: "var(--k-space-4)",
          }}
        >
          {/* Search Input */}
          <div style={{ flex: "1 1 240px", minWidth: 200, display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="log-search" className="k-xs k-faint" style={{ whiteSpace: "nowrap" }}>
              Search:
            </label>
            <input
              id="log-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by event, detail, or incident..."
              style={{
                width: "100%",
                padding: "6px 10px",
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border)",
                background: "var(--k-surface)",
                color: "var(--k-text)",
                fontFamily: "var(--k-font-mono)",
                fontSize: 12,
                outline: "none",
              }}
            />
          </div>

          {/* Level Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="level-filter" className="k-xs k-faint" style={{ whiteSpace: "nowrap" }}>
              Severity:
            </label>
            <select
              id="level-filter"
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value)}
              style={{
                padding: "6px 10px",
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border)",
                background: "var(--k-surface)",
                color: "var(--k-text)",
                fontSize: 12,
              }}
            >
              <option value="all">All Severities</option>
              <option value="warning">Warning & Above</option>
              <option value="error">Error & Critical</option>
              <option value="info">Info</option>
            </select>
          </div>

          {/* Logger / Source Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="logger-filter" className="k-xs k-faint" style={{ whiteSpace: "nowrap" }}>
              Source:
            </label>
            <select
              id="logger-filter"
              value={selectedLogger}
              onChange={(e) => setSelectedLogger(e.target.value)}
              style={{
                padding: "6px 10px",
                borderRadius: "var(--k-radius-sm)",
                border: "1px solid var(--k-border)",
                background: "var(--k-surface)",
                color: "var(--k-text)",
                fontSize: 12,
              }}
            >
              <option value="all">All Subsystems</option>
              {availableLoggers.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          {(search || selectedLevel !== "all" || selectedLogger !== "all") && (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setSelectedLevel("all");
                setSelectedLogger("all");
              }}
              className="k-xs k-muted"
              style={{
                background: "none",
                border: "1px dashed var(--k-border)",
                padding: "5px 8px",
                borderRadius: "var(--k-radius-sm)",
                cursor: "pointer",
              }}
            >
              Reset filters
            </button>
          )}
        </section>

        {/* Failed / Error Message */}
        {failed && (
          <p
            role="alert"
            className="k-sm"
            style={{
              padding: "var(--k-space-3)",
              borderRadius: "var(--k-radius-sm)",
              border: "1px solid var(--k-risk-high)",
              background: "var(--k-risk-high-bg)",
              color: "var(--k-risk-high)",
              marginBottom: "var(--k-space-4)",
            }}
          >
            {failed}
          </p>
        )}

        {/* Log Stream Content */}
        {loading && logs.length === 0 ? (
          <p
            className="k-sm k-muted"
            style={{
              padding: "var(--k-space-4)",
              textAlign: "center",
              border: "1px dashed var(--k-border)",
              borderRadius: "var(--k-radius-sm)",
            }}
          >
            Loading control plane log stream...
          </p>
        ) : filtered.length === 0 ? (
          <p
            className="k-sm k-muted"
            style={{
              padding: "var(--k-space-4)",
              textAlign: "center",
              border: "1px dashed var(--k-border)",
              borderRadius: "var(--k-radius-sm)",
            }}
          >
            {logs.length === 0
              ? "Nothing logged yet. The control plane is deliberately quiet — there are four log statements in it, and the audit trail carries the decisions."
              : "No logs match the current search and severity filters."}
          </p>
        ) : (
          <div
            className="k-scroll"
            style={{
              overflowX: "auto",
              border: "1px solid var(--k-border)",
              borderRadius: "var(--k-radius-sm)",
              background: "var(--k-surface)",
              boxShadow: "0 2px 12px rgba(0, 0, 0, 0.2)",
            }}
          >
            <table
              className="k-mono k-sm"
              style={{
                width: "100%",
                borderCollapse: "collapse",
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "var(--k-surface-sunken)",
                    borderBottom: "1px solid var(--k-border)",
                    color: "var(--k-text-muted)",
                    fontSize: 11,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  <th style={{ padding: "8px 12px", width: 140 }}>Timestamp</th>
                  <th style={{ padding: "8px 12px", width: 90 }}>Level</th>
                  <th style={{ padding: "8px 12px", width: 150 }}>Subsystem</th>
                  <th style={{ padding: "8px 12px", width: 130 }}>Incident</th>
                  <th style={{ padding: "8px 12px" }}>Message / Event</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr
                    key={`${r.at}-${i}`}
                    style={{
                      borderBottom: "1px solid var(--k-border-subtle)",
                      background:
                        r.level === "error" || r.level === "critical"
                          ? "rgba(239, 68, 68, 0.05)"
                          : "transparent",
                    }}
                  >
                    {/* Timestamp */}
                    <td
                      className="k-muted"
                      style={{
                        padding: "6px 12px",
                        whiteSpace: "nowrap",
                        verticalAlign: "top",
                        fontSize: 12,
                      }}
                      title={r.at}
                    >
                      {r.at.slice(11, 23) || r.at}
                    </td>

                    {/* Level Badge */}
                    <td style={{ padding: "6px 12px", verticalAlign: "top" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "1px 6px",
                          borderRadius: "var(--k-radius-sm)",
                          background: LEVEL_BG[r.level] || "var(--k-surface-raised)",
                          color: LEVEL_COLOR[r.level] || "var(--k-text)",
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                        }}
                      >
                        {r.level}
                      </span>
                    </td>

                    {/* Subsystem / Logger */}
                    <td
                      className="k-muted"
                      style={{
                        padding: "6px 12px",
                        verticalAlign: "top",
                        fontSize: 12,
                        wordBreak: "break-all",
                      }}
                    >
                      {r.logger || "—"}
                    </td>

                    {/* Incident ID */}
                    <td style={{ padding: "6px 12px", verticalAlign: "top" }}>
                      {r.incident_id ? (
                        <Link
                          href={`/traces?incident_id=${r.incident_id}`}
                          className="k-mono-sm"
                          style={{
                            color: "var(--k-accent)",
                            textDecoration: "none",
                            fontWeight: 600,
                          }}
                          title={`Investigate traces for ${r.incident_id}`}
                        >
                          {r.incident_id}
                        </Link>
                      ) : (
                        <span className="k-faint">—</span>
                      )}
                    </td>

                    {/* Event & Detail & Exception */}
                    <td style={{ padding: "6px 12px", verticalAlign: "top" }}>
                      <div style={{ wordBreak: "break-word" }}>
                        <span style={{ fontWeight: 600, color: "var(--k-text)" }}>
                          {r.event}
                        </span>
                        {r.detail && (
                          <span className="k-muted" style={{ marginLeft: 6 }}>
                            {r.detail}
                          </span>
                        )}
                      </div>

                      {/* Exception stack trace disclosure */}
                      {r.exception && (
                        <details style={{ marginTop: 6 }}>
                          <summary
                            className="k-xs"
                            style={{
                              color: "var(--k-risk-high)",
                              cursor: "pointer",
                              fontWeight: 600,
                            }}
                          >
                            Traceback / Exception Details
                          </summary>
                          <pre
                            className="k-mono k-scroll"
                            style={{
                              margin: "6px 0 0",
                              maxHeight: 180,
                              overflow: "auto",
                              background: "var(--k-surface-lowest)",
                              padding: "var(--k-space-2)",
                              borderRadius: "var(--k-radius-sm)",
                              border: "1px solid var(--k-border)",
                              color: "var(--k-risk-high)",
                              fontSize: 11,
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-all",
                            }}
                          >
                            {r.exception}
                          </pre>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

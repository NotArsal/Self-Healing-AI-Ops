/**
 * The dedicated Traces screen — Phase 9.4.
 *
 * Distributed-tracing entry point and incident trace context.
 * Reuses the Jaeger and Grafana integrations configured via:
 *   NEXT_PUBLIC_KAVACH_JAEGER (default: http://localhost:16686)
 *   NEXT_PUBLIC_KAVACH_GRAFANA (default: http://localhost:3002)
 *
 * Links directly to traces using the span attribute `kavach.incident_id`.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { api, type LlmCall } from "@/lib/api";
import { GRAFANA_BASE, JAEGER_BASE, traceUrl } from "@/lib/traces";
import { useSystem } from "@/lib/live";



export default function TracesPage() {
  const { system } = useSystem();
  const [calls, setCalls] = useState<LlmCall[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState("");
  const [incidentQuery, setIncidentQuery] = useState("");

  // Read ?incident_id= from URL on mount
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const inc = params.get("incident_id");
      if (inc) setIncidentQuery(inc);
    } catch {
      // Ignore in non-browser env
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await api.GET("/v1/llm-calls");
    setLoading(false);
    if (error || !data) {
      setFailed("Could not fetch trace context. Is the control plane up?");
      return;
    }
    setFailed("");
    setCalls(data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const targetTraceUrl = incidentQuery.trim()
    ? traceUrl(incidentQuery.trim())
    : `${JAEGER_BASE}/search?service=kavach-control-plane&operation=kavach.heal`;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current="/traces"
      />

      <main
        className="k-scroll"
        style={{
          flex: 1,
          padding: "var(--k-space-4) var(--k-space-5)",
          overflowY: "auto",
        }}
      >
        {/* Header */}
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
                <Icon name="git-commit" size={16} />
              </span>
              <h1 style={{ margin: 0 }}>Traces</h1>
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
                OpenTelemetry Instrumented
              </span>
            </div>
            <p className="k-sm k-muted" style={{ margin: "4px 0 0", maxWidth: "80ch" }}>
              Distributed tracing entry point for autonomous self-healing loops. Each loop run
              emits a root span (<code className="k-mono-sm">kavach.heal</code>) with child spans
              for detection, diagnosis, gate evaluation, action execution, and verification.
            </p>
          </div>

          <div style={{ display: "flex", gap: "var(--k-space-2)", flexWrap: "wrap" }}>
            <a
              href={`${JAEGER_BASE}/search?service=kavach-control-plane&operation=kavach.heal`}
              target="_blank"
              rel="noreferrer"
              className="k-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 12px",
                border: "1px solid var(--k-border-strong)",
                borderRadius: "var(--k-radius-sm)",
                background: "var(--k-surface-raised)",
                color: "var(--k-text)",
                textDecoration: "none",
                fontWeight: 600,
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
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 12px",
                border: "1px solid var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
                background: "var(--k-surface-sunken)",
                color: "var(--k-text-muted)",
                textDecoration: "none",
              }}
            >
              Metric history in Grafana →
            </a>
          </div>
        </header>

        {/* Integration Status & Endpoint Info Strip */}
        <section
          aria-label="Trace explorer configuration"
          className="k-card"
          style={{
            marginBottom: "var(--k-space-4)",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "var(--k-space-3)",
            padding: "var(--k-space-3) var(--k-space-4)",
            background: "var(--k-surface-sunken)",
          }}
        >
          <div>
            <span className="k-xs k-faint" style={{ display: "block" }}>Configured Jaeger UI</span>
            <a
              href={JAEGER_BASE}
              target="_blank"
              rel="noreferrer"
              className="k-mono-sm"
              style={{ color: "var(--k-accent)", textDecoration: "none", fontWeight: 600 }}
            >
              {JAEGER_BASE}
            </a>
          </div>
          <div>
            <span className="k-xs k-faint" style={{ display: "block" }}>OTel Service Name</span>
            <span className="k-mono-sm" style={{ color: "var(--k-text)" }}>
              kavach-control-plane
            </span>
          </div>
          <div>
            <span className="k-xs k-faint" style={{ display: "block" }}>Root Span Operation</span>
            <span className="k-mono-sm" style={{ color: "var(--k-text)" }}>
              kavach.heal
            </span>
          </div>
          <div>
            <span className="k-xs k-faint" style={{ display: "block" }}>Correlation Tag</span>
            <span className="k-mono-sm" style={{ color: "var(--k-accent)" }}>
              kavach.incident_id
            </span>
          </div>
        </section>

        {/* Incident Trace Search Box */}
        <section
          aria-label="Lookup trace by incident ID"
          className="k-card"
          style={{
            marginBottom: "var(--k-space-4)",
            padding: "var(--k-space-4)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--k-space-2)",
          }}
        >
          <h2 style={{ fontSize: 16, margin: 0 }}>Incident Trace Lookup</h2>
          <p className="k-sm k-muted" style={{ margin: 0 }}>
            Enter an incident identifier to query Jaeger directly for the exact distributed trace.
          </p>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--k-space-2)",
              flexWrap: "wrap",
              marginTop: "var(--k-space-1)",
            }}
          >
            <div style={{ flex: "1 1 280px", minWidth: 200 }}>
              <label htmlFor="trace-incident-input" className="k-sr-only">
                Incident ID
              </label>
              <input
                id="trace-incident-input"
                type="text"
                value={incidentQuery}
                onChange={(e) => setIncidentQuery(e.target.value)}
                placeholder="e.g. INC-104512"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "var(--k-radius-sm)",
                  border: "1px solid var(--k-border)",
                  background: "var(--k-surface-sunken)",
                  color: "var(--k-text)",
                  fontFamily: "var(--k-font-mono)",
                  fontSize: 13,
                  outline: "none",
                }}
              />
            </div>

            <a
              href={targetTraceUrl}
              target="_blank"
              rel="noreferrer"
              className="k-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 16px",
                borderRadius: "var(--k-radius-sm)",
                border: "none",
                background: "var(--k-loop-gradient)",
                color: "var(--k-text-inverse)",
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              Open in Jaeger →
            </a>

            {incidentQuery && (
              <button
                type="button"
                onClick={() => setIncidentQuery("")}
                className="k-xs k-muted"
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "6px 8px",
                }}
              >
                Clear
              </button>
            )}
          </div>
        </section>

        {/* Failed state if API is down */}
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

        {/* Available Incident Traces List */}
        <section style={{ marginBottom: "var(--k-space-5)" }}>
          <header
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "var(--k-space-3)",
              marginBottom: "var(--k-space-2)",
            }}
          >
            <h2 style={{ fontSize: 16, margin: 0 }}>Recorded Autonomous Traces</h2>
            <span className="k-mono-sm k-faint" style={{ fontSize: 11 }}>
              {calls.length} runs recorded
            </span>
          </header>
          <p className="k-sm k-muted" style={{ margin: "0 0 var(--k-space-3)" }}>
            Real execution traces available from recorded autonomous loops. Selecting an incident opens
            the exact trace in the configured external viewer.
          </p>

          {loading && calls.length === 0 ? (
            <p
              className="k-sm k-muted"
              style={{
                padding: "var(--k-space-4)",
                textAlign: "center",
                border: "1px dashed var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
              }}
            >
              Loading trace context...
            </p>
          ) : calls.length === 0 ? (
            <p
              className="k-sm k-muted"
              style={{
                margin: 0,
                padding: "var(--k-space-4)",
                border: "1px dashed var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
                textAlign: "center",
              }}
            >
              No traces recorded yet. Traces are emitted during autonomous loop execution.
            </p>
          ) : (
            <div
              className="k-scroll"
              style={{
                overflowX: "auto",
                border: "1px solid var(--k-border)",
                borderRadius: "var(--k-radius-sm)",
                background: "var(--k-surface)",
              }}
            >
              <table
                className="k-mono k-sm"
                style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}
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
                    <th style={{ padding: "8px 12px" }}>Incident ID</th>
                    <th style={{ padding: "8px 12px" }}>Fault Class</th>
                    <th style={{ padding: "8px 12px" }}>Model</th>
                    <th style={{ padding: "8px 12px" }}>Latency</th>
                    <th style={{ padding: "8px 12px" }}>Timestamp</th>
                    <th style={{ padding: "8px 12px", textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c, i) => (
                    <tr
                      key={`${c.incident_id}-${i}`}
                      style={{ borderBottom: "1px solid var(--k-border-subtle)" }}
                    >
                      <td style={{ padding: "8px 12px", fontWeight: 700, color: "var(--k-accent)" }}>
                        {c.incident_id}
                      </td>
                      <td style={{ padding: "8px 12px" }}>{c.fault_class || "—"}</td>
                      <td style={{ padding: "8px 12px", color: "var(--k-text-muted)" }}>{c.model}</td>
                      <td style={{ padding: "8px 12px" }}>{c.latency_s}s</td>
                      <td style={{ padding: "8px 12px", color: "var(--k-text-muted)" }}>
                        {c.at.slice(11, 19) || c.at}
                      </td>
                      <td style={{ padding: "8px 12px", textAlign: "right" }}>
                        <a
                          href={traceUrl(c.incident_id)}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            color: "var(--k-accent)",
                            textDecoration: "none",
                            fontWeight: 600,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                          }}
                        >
                          Trace in Jaeger →
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Tracing Architecture Guide */}
        <section
          aria-label="Tracing architecture"
          className="k-card"
          style={{
            padding: "var(--k-space-4)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--k-space-2)",
          }}
        >
          <h2 style={{ fontSize: 16, margin: 0 }}>OpenTelemetry Trace Architecture (ADR 0018)</h2>
          <p className="k-sm k-muted" style={{ margin: 0, maxWidth: "80ch" }}>
            Kavach instrumentation avoids in-process span duplication. The telemetry layer emits
            standard OpenTelemetry Protocol (OTLP) gRPC spans to the local collector daemon.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "var(--k-space-2)",
              marginTop: "var(--k-space-2)",
            }}
          >
            <div style={{ padding: "var(--k-space-2)", background: "var(--k-surface-sunken)", borderRadius: "var(--k-radius-sm)" }}>
              <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-accent)" }}>
                01. detect & collect
              </span>
              <p className="k-xs k-muted" style={{ margin: "2px 0 0" }}>
                Records metric window evaluation and log anomaly evidence retrieval.
              </p>
            </div>
            <div style={{ padding: "var(--k-space-2)", background: "var(--k-surface-sunken)", borderRadius: "var(--k-radius-sm)" }}>
              <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-accent)" }}>
                02. diagnose & gate
              </span>
              <p className="k-xs k-muted" style={{ margin: "2px 0 0" }}>
                Records model inference duration, tokens consumed, and deterministic safety checks.
              </p>
            </div>
            <div style={{ padding: "var(--k-space-2)", background: "var(--k-surface-sunken)", borderRadius: "var(--k-radius-sm)" }}>
              <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-accent)" }}>
                03. execute & verify
              </span>
              <p className="k-xs k-muted" style={{ margin: "2px 0 0" }}>
                Records inverse capture, patch write, probe synthesis, and rollback if triggered.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

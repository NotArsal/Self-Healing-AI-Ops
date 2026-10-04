/**
 * The onboarding / preflight screen.
 *
 * It exposes the existing read-only check registry and nothing else — no new
 * onboarding logic, per the P4 scope. A SKIP is rendered as blocking, not as a
 * pass, because `PreflightReport.passed` treats unknown as unhealthy and the
 * screen must not disagree with the backend about what blocks enablement.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { api, type Preflight } from "@/lib/api";
import { useSystem } from "@/lib/live";

export default function PreflightPage() {
  const { system } = useSystem();
  const [report, setReport] = useState<Preflight | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await api.GET("/v1/preflight");
    setLoading(false);
    if (error || !data) {
      setFailed("Could not run preflight. Is the control plane up?");
      return;
    }
    setFailed("");
    setReport(data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current="/preflight"
      />

      <main
        className="k-scroll"
        style={{
          flex: 1,
          padding: "var(--k-space-5) var(--k-space-6)",
          minWidth: 0,
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "var(--k-space-4)",
            marginBottom: "var(--k-space-4)",
            maxWidth: 1040,
          }}
        >
          <div>
            <h1>Onboarding and preflight</h1>
            <p className="k-sm k-muted" style={{ margin: "4px 0 0", maxWidth: "72ch" }}>
              Every check is read-only. A skipped check blocks enablement, because
              unknown is not healthy.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            style={{
              minHeight: 40,
              padding: "0 var(--k-space-4)",
              borderRadius: "var(--k-radius-md)",
              border: "1px solid var(--k-border-strong)",
              background: "var(--k-surface-raised)",
              color: "var(--k-text)",
            }}
          >
            {loading ? "Running" : "Run preflight"}
          </button>
        </header>

        {failed && (
          <p role="alert" className="k-sm" style={{ color: "var(--k-risk-high)" }}>
            {failed}
          </p>
        )}

        {report && (
          <>
            <p
              className="k-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                margin: "0 0 var(--k-space-4)",
                padding: "var(--k-space-2) var(--k-space-3)",
                borderRadius: "var(--k-radius-md)",
                border: `1px solid ${report.passed ? "var(--k-risk-low)" : "var(--k-risk-high)"}`,
                background: report.passed
                  ? "var(--k-risk-low-bg)"
                  : "var(--k-risk-high-bg)",
                color: report.passed ? "var(--k-risk-low)" : "var(--k-risk-high)",
              }}
            >
              <Icon name={report.passed ? "check" : "cross"} />
              {report.passed
                ? `Preflight passed · ${report.checks.length} checks`
                : `Preflight blocked · ${report.blocking_count} of ${report.checks.length} checks`}
            </p>

            {report.error && (
              <p className="k-sm" style={{ color: "var(--k-risk-high)" }}>
                {report.error}
              </p>
            )}

            <table
              className="k-sm"
              style={{
                width: "100%",
                maxWidth: 1040,
                borderCollapse: "collapse",
                textAlign: "left",
              }}
            >
              <caption className="k-sr-only">
                Preflight checks for {report.project}, with status and remediation.
              </caption>
              <thead>
                <tr className="k-xs k-faint">
                  <th scope="col" style={{ padding: "8px", fontWeight: 500, width: 90 }}>
                    Status
                  </th>
                  <th scope="col" style={{ padding: "8px", fontWeight: 500, width: 260 }}>
                    Check
                  </th>
                  <th scope="col" style={{ padding: "8px", fontWeight: 500 }}>
                    Detail
                  </th>
                </tr>
              </thead>
              <tbody>
                {report.checks.map((check) => {
                  const colour = check.skipped
                    ? "var(--k-risk-med)"
                    : check.passed
                      ? "var(--k-risk-low)"
                      : "var(--k-risk-high)";
                  return (
                    <tr
                      key={check.name}
                      style={{ borderTop: "1px solid var(--k-border-subtle)" }}
                    >
                      <td style={{ padding: "8px", verticalAlign: "top" }}>
                        <span
                          className="k-xs"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            color: colour,
                          }}
                        >
                          <Icon
                            name={
                              check.skipped
                                ? "info"
                                : check.passed
                                  ? "check"
                                  : "cross"
                            }
                          />
                          {check.status}
                        </span>
                      </td>
                      <td
                        className="k-mono-sm"
                        style={{ padding: "8px", verticalAlign: "top" }}
                      >
                        {check.name}
                      </td>
                      <td style={{ padding: "8px", verticalAlign: "top" }}>
                        <span className="k-muted">{check.detail}</span>
                        {check.remediation && !check.passed && (
                          <span
                            className="k-mono-sm"
                            style={{ display: "block", marginTop: 4, color: colour }}
                          >
                            {check.remediation}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </main>
    </div>
  );
}

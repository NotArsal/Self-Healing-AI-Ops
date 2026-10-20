/**
 * The verification strip — DESIGN_SYSTEM.md §7.8.
 *
 * Three probes in a row, all visibly present before they run so a missing
 * probe is obvious. The third is labelled "fast quality", never "eval": the
 * live loop runs 3 deterministic cases (FR-07) and never the 40-case research
 * evaluator (FR-07a), and calling it "eval" would imply a run that is not
 * happening.
 *
 * THE SLO WINDOW PROBE IS NOT IMPLEMENTED. It renders as permanently pending
 * with a title saying so, because that is the truth: fast verification ships
 * two of the three FR-07 probes and the window probe lands in P6. Hiding it
 * would make a two-probe verification look like a three-probe one.
 */

import { Sparkline } from "../charts/Sparkline";
import { Icon } from "../ui/Icon";
import { ProbePill } from "../ui/pills";
import type { Incident, Verification } from "@/lib/api";

const probeState = (
  value: boolean | null | undefined,
): "pending" | "passed" | "failed" =>
  value === null || value === undefined ? "pending" : value ? "passed" : "failed";

export function VerificationStrip({
  verification,
  incident,
}: {
  verification: Verification | null;
  incident: Incident | null;
}) {
  const v = verification;
  const corpusUnchanged = incident?.corpus_unchanged ?? null;

  return (
    <section
      aria-labelledby="verification-heading"
      className="k-card"
      style={{ display: "flex", flexDirection: "column", gap: "var(--k-space-3)" }}
    >
      <h3 id="verification-heading">Verification</h3>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--k-space-2)" }}>
        <ProbePill
          label="health"
          state={probeState(v?.health_ok)}
          detail={v?.health_detail || "target /healthz"}
        />
        <ProbePill
          label="SLO window"
          state="pending"
          detail="Not implemented: the 120s SLO-window probe is the FR-07 probe still missing. Scheduled in P6."
        />
        <ProbePill
          label="fast quality"
          state={probeState(v?.quality_ok)}
          detail={
            v
              ? `${v.cases.filter((c) => c.passed).length}/${v.cases.length} cases in ${v.total_s}s, budget ${v.budget_s}s`
              : "3 deterministic cases, serial"
          }
        />
      </div>

      {v && (
        <>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "var(--k-space-2) var(--k-space-3)",
              background: "var(--k-surface-sunken)",
              border: "1px solid var(--k-border-subtle)",
              borderRadius: "var(--k-radius-sm)",
              gap: "var(--k-space-2)",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span className="k-xs k-faint">Fast quality budget</span>
              <span className="k-mono-sm">
                {v.total_s}s <span className="k-faint">/ {v.budget_s}s budget</span>
              </span>
            </div>
            <Sparkline
              type="bullet"
              data={[v.total_s]}
              threshold={v.budget_s}
              max={Math.max(v.budget_s, v.total_s * 1.15)}
              label="Quality evaluation duration"
              unit="s"
              width={110}
              height={8}
            />
          </div>

          {v.cases.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                margin: "2px 0",
              }}
            >
              <span className="k-xs k-faint">Case latencies</span>
              <Sparkline
                type="bar"
                data={v.cases.map((c) => c.latency_s)}
                label="Case probe latencies"
                unit="s"
                width={70}
                height={14}
                color="var(--k-state-healing)"
              />
            </div>
          )}

          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {v.cases.map((c) => (
              <li
                key={c.case_id}
                className="k-sm"
                style={{
                  display: "grid",
                  gridTemplateColumns: "16px 70px 1fr auto",
                  gap: "var(--k-space-2)",
                  alignItems: "center",
                  padding: "3px 0",
                }}
              >
                <span
                  style={{
                    display: "flex",
                    color: c.passed ? "var(--k-risk-low)" : "var(--k-risk-high)",
                  }}
                >
                  <Icon name={c.passed ? "check" : "cross"} />
                </span>
                <span className="k-mono-sm">{c.case_id}</span>
                <span className="k-faint k-mono-sm">
                  keyword {c.keyword_present ? "yes" : "no"} · answered{" "}
                  {c.non_refusal ? "yes" : "no"} · grounded{" "}
                  {c.sources_block ? "yes" : "no"}
                </span>
                <span className="k-mono-sm k-faint">{c.latency_s}s</span>
              </li>
            ))}
          </ul>

          <dl
            style={{
              margin: 0,
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: "4px var(--k-space-3)",
            }}
          >
            {v.repair_applied && (
              <>
                <dt className="k-xs k-faint">repair applied</dt>
                <dd className="k-sm" style={{ margin: 0 }}>
                  {v.repair_applied.ok ? "yes" : "no"} —{" "}
                  <span className="k-muted">{v.repair_applied.detail}</span>
                </dd>
              </>
            )}
            {v.scope_respected && (
              <>
                <dt className="k-xs k-faint">scope respected</dt>
                <dd className="k-sm" style={{ margin: 0 }}>
                  {v.scope_respected.ok ? "yes" : "no"} —{" "}
                  <span className="k-muted">{v.scope_respected.detail}</span>
                </dd>
              </>
            )}
            <dt className="k-xs k-faint">corpus</dt>
            <dd className="k-sm k-mono-sm" style={{ margin: 0 }}>
              {corpusUnchanged === null
                ? "not fingerprinted yet"
                : corpusUnchanged
                  ? `unchanged · ${incident?.corpus_after?.chunks ?? "?"} chunks / ${incident?.corpus_after?.files ?? "?"} files`
                  : "CHANGED — this blocks resolution"}
            </dd>
            {incident?.action?.config_hash_after && (
              <>
                <dt className="k-xs k-faint">final config hash</dt>
                <dd className="k-sm k-mono-sm" style={{ margin: 0 }}>
                  {incident.action.config_hash_after}
                </dd>
              </>
            )}
          </dl>
        </>
      )}

      {incident && (
        <p
          className="k-sm"
          style={{
            margin: 0,
            paddingTop: "var(--k-space-2)",
            borderTop: "1px solid var(--k-border-subtle)",
          }}
        >
          <span className="k-faint">Final state </span>
          <strong>{incident.status}</strong>
          {incident.outcome ? (
            <span className="k-muted"> · {incident.outcome}</span>
          ) : null}
          {incident.escalation_reason ? (
            <span style={{ color: "var(--k-risk-high)" }}>
              {" "}
              · {incident.escalation_reason}
            </span>
          ) : null}
        </p>
      )}
    </section>
  );
}

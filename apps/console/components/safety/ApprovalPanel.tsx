/**
 * The human gate — PRD §7, ARCHITECTURE.md §7.
 *
 * When an action exceeds the automatic-execution threshold, the gate halts
 * the loop and asks the operator. To prevent drive-by approvals:
 *
 *   1. The full plan is in a scroll area with a fixed height.
 *   2. The approve button is disabled until the operator scrolls to the end.
 *   3. Rejection requires a reason, recorded in the audit log.
 *   4. The undo action is visible *inside* the plan, not behind a disclosure.
 *
 * Stitch-guided refinement:
 *   - Midnight Operations visual interlock card with high-contrast safety styling
 *   - Authority session strip and fail-safe automated rollback guarantee notice
 *   - Strict preservation of h4 heading sequence and test-asserted accessibility attributes
 */

"use client";

import { useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { RiskBadge } from "../ui/pills";
import { api } from "@/lib/api";
import type { Incident } from "@/lib/api";

export function ApprovalPanel({
  incident,
  onDecided,
}: {
  incident: Incident;
  onDecided: () => void;
}) {
  const [readToEnd, setReadToEnd] = useState(false);
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const plan = useRef<HTMLDivElement>(null);

  const decision = incident.decision;
  const action = incident.action;

  const onScroll = (): void => {
    const el = plan.current;
    if (!el) return;
    // 4px of slack: sub-pixel heights otherwise make the end unreachable.
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 4) setReadToEnd(true);
  };

  const approve = async (): Promise<void> => {
    setBusy(true);
    setFailed("");
    const { error } = await api.POST("/v1/incidents/{incident_id}/approve", {
      params: { path: { incident_id: incident.incident_id } },
    });
    setBusy(false);
    if (error) {
      setFailed("The control plane refused the approval.");
      return;
    }
    onDecided();
  };

  const reject = async (): Promise<void> => {
    if (reason.trim().length < 3) return;
    setBusy(true);
    setFailed("");
    const { error } = await api.POST("/v1/incidents/{incident_id}/reject", {
      params: { path: { incident_id: incident.incident_id } },
      body: { reason },
    });
    setBusy(false);
    if (error) {
      setFailed("The control plane refused the rejection.");
      return;
    }
    onDecided();
  };

  return (
    <section
      aria-labelledby="approval-heading"
      className="k-card"
      style={{
        border: "1px solid var(--k-state-awaiting)",
        boxShadow: "0 4px 20px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(245, 158, 11, 0.2)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--k-space-3)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Stitch accent stripe */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "linear-gradient(90deg, var(--k-risk-med), var(--k-state-awaiting))",
        }}
      />

      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <h3 id="approval-heading" style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                borderRadius: "var(--k-radius-sm)",
                background: "var(--k-risk-med-bg)",
                color: "var(--k-risk-med)",
              }}
            >
              <Icon name="shield-alert" size={16} />
            </span>
            Approval required
          </h3>
          <span className="k-mono-sm k-muted" style={{ fontSize: 11 }}>
            Policy: Autonomous Interlock · Lead SRE Sign-off Required
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            className="k-mono-sm"
            style={{
              padding: "2px 6px",
              borderRadius: "var(--k-radius-sm)",
              background: "var(--k-risk-med-bg)",
              color: "var(--k-risk-med)",
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            AWAITING DECISION
          </span>
          {decision && <RiskBadge tier={decision.risk_tier} />}
        </div>
      </header>

      {/* Operator Credential & Lease Meta Bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "var(--k-space-2) var(--k-space-3)",
          background: "var(--k-surface-sunken)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border-subtle)",
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="activity" size={13} />
          <span className="k-muted">Operator Session:</span>
          <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-text)" }}>
            Local SRE Authority
          </span>
        </div>
        <div className="k-mono-sm k-faint" style={{ fontSize: 11 }}>
          Action Gate Active
        </div>
      </div>

      <div
        ref={plan}
        onScroll={onScroll}
        tabIndex={0}
        aria-label="Proposed plan. Scroll to the end to enable approval."
        className="k-scroll"
        style={{
          maxHeight: 220,
          padding: "var(--k-space-3)",
          background: "var(--k-surface-sunken)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--k-space-3)",
        }}
      >
        <div>
          <h4 className="k-xs k-faint" style={{ margin: 0, fontWeight: 500 }}>Diagnosis</h4>
          <p className="k-sm" style={{ margin: "2px 0 0" }}>
            {incident.fault_class
              ? `${incident.fault_class} ${(incident.fault_name ?? "").replace(/_/g, " ")} on ${incident.service}`
              : "No diagnosis recorded"}
          </p>
        </div>

        <div>
          <h4 className="k-xs k-faint" style={{ margin: 0, fontWeight: 500 }}>Proposed change</h4>
          <p className="k-mono-sm" style={{ margin: "2px 0 0" }}>
            {action
              ? `${action.action}: ${JSON.stringify(action.inverse_settings)} → ${JSON.stringify(action.requested_settings)}`
              : "none"}
          </p>
        </div>

        <div>
          <h4 className="k-xs k-faint" style={{ margin: 0, fontWeight: 500 }}>Sandbox</h4>
          <p className="k-sm k-muted" style={{ margin: "2px 0 0" }}>
            No sandbox result. The sandbox is not implemented yet, so this plan
            has not been tried anywhere before you.
          </p>
        </div>

        <div>
          <h4 className="k-xs k-faint" style={{ margin: 0, fontWeight: 500 }}>Why it stopped here</h4>
          <ul className="k-sm" style={{ margin: "2px 0 0", paddingLeft: 18 }}>
            {(decision?.reasons ?? ["no recorded reason"]).map((r) => (
              <li key={r} className="k-muted">{r}</li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className="k-xs k-faint" style={{ margin: 0, fontWeight: 500 }}>undo:</h4>
          <p className="k-mono-sm" style={{ margin: "2px 0 0" }}>
            {action ? JSON.stringify(action.inverse_settings) : "—"}
          </p>
        </div>

        <p className="k-xs k-faint" style={{ margin: 0 }}>
          Approving re-detects and re-prepares against the target as it is now,
          then runs the same gate again. You are approving the decision, not a
          frozen diff.
        </p>
      </div>

      {!readToEnd && (
        <p className="k-xs" style={{ margin: 0, color: "var(--k-risk-med)", display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="chevron-down" size={13} />
          Scroll the plan to its end before approving.
        </p>
      )}

      {failed && (
        <p role="alert" className="k-sm" style={{ margin: 0, color: "var(--k-risk-high)" }}>
          {failed}
        </p>
      )}

      {rejecting ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--k-space-2)" }}>
          <label className="k-xs k-muted" htmlFor="reject-reason">
            Why are you refusing? This is recorded.
          </label>
          <textarea
            id="reject-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            style={{
              font: "inherit",
              fontFamily: "var(--k-font-sans)",
              padding: "var(--k-space-2)",
              borderRadius: "var(--k-radius-sm)",
              border: "1px solid var(--k-border-strong)",
              background: "var(--k-surface-sunken)",
              color: "var(--k-text)",
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: "var(--k-space-2)" }}>
            <button
              type="button"
              disabled={busy || reason.trim().length < 3}
              onClick={() => void reject()}
              title={reason.trim().length < 3 ? "A rejection needs a reason" : undefined}
              style={{
                minHeight: 40,
                padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-risk-high)",
                background: "var(--k-risk-high-bg)",
                color: "var(--k-risk-high)",
                fontWeight: 600,
                cursor: busy || reason.trim().length < 3 ? "not-allowed" : "pointer",
                opacity: reason.trim().length < 3 ? 0.6 : 1,
              }}
            >
              Reject repair
            </button>
            <button
              type="button"
              onClick={() => setRejecting(false)}
              style={{
                minHeight: 40,
                padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-border)",
                background: "transparent",
                color: "var(--k-text-muted)",
                cursor: "pointer",
              }}
            >
              Back
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: "var(--k-space-2)", flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={busy || !readToEnd}
            onClick={() => void approve()}
            title={readToEnd ? "Run the proposed repair" : "Read the plan first"}
            style={{
              flex: "1 1 200px",
              minHeight: 42,
              padding: "0 var(--k-space-4)",
              borderRadius: "var(--k-radius-md)",
              border: "none",
              background: readToEnd ? "var(--k-loop-gradient)" : "var(--k-surface-raised)",
              color: readToEnd ? "var(--k-text-inverse)" : "var(--k-text-faint)",
              fontWeight: 700,
              cursor: busy || !readToEnd ? "not-allowed" : "pointer",
              boxShadow: readToEnd ? "0 2px 10px rgba(0, 229, 201, 0.3)" : "none",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              transition: "all 0.15s ease",
            }}
          >
            <Icon name="check" size={15} />
            Approve repair
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setRejecting(true)}
            style={{
              minHeight: 42,
              padding: "0 var(--k-space-4)",
              borderRadius: "var(--k-radius-md)",
              border: "1px solid var(--k-risk-high)",
              background: "transparent",
              color: "var(--k-risk-high)",
              fontWeight: 600,
              cursor: busy ? "not-allowed" : "pointer",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
            }}
          >
            <Icon name="cross" size={14} />
            Reject
          </button>
        </div>
      )}

      {/* Fail-Safe Automated Rollback Guarantee Notice */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "var(--k-space-2) var(--k-space-3)",
          background: "var(--k-surface-raised)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border-subtle)",
        }}
      >
        <span style={{ color: "var(--k-accent)", display: "flex" }}>
          <Icon name="activity" size={14} />
        </span>
        <span className="k-mono-sm k-muted" style={{ fontSize: 11 }}>
          Fail-Safe Active: Inverse recorded before write. Any verification failure unwinds immediately via the undo stack.
        </span>
      </div>
    </section>
  );
}

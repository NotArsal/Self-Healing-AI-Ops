/**
 * The approval panel — DESIGN_SYSTEM.md §7.7.
 *
 * Order is fixed: diagnosis → proposed change → sandbox result → risk
 * rationale → inverse → controls. The operator learns the position.
 *
 * THE APPROVE BUTTON IS DISABLED UNTIL THE PLAN HAS BEEN SCROLLED TO ITS END.
 * Approving unread is the failure mode this product exists to prevent, and a
 * gate whose button can be clicked without looking is theatre. Rejecting needs
 * no scroll — refusing without reading is safe.
 *
 * Reject requires a reason, enforced here and again by the API, because a
 * refusal without one teaches nobody anything.
 */

"use client";

import { useRef, useState } from "react";

import { Icon } from "../ui/Icon";
import { RiskBadge } from "../ui/pills";
import { api, type Incident } from "@/lib/api";

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
        borderColor: "var(--k-state-awaiting)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--k-space-3)",
      }}
    >
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <h3 id="approval-heading" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Icon name="shield-alert" />
          Approval required
        </h3>
        {decision && <RiskBadge tier={decision.risk_tier} />}
      </header>

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
        <p className="k-xs" style={{ margin: 0, color: "var(--k-risk-med)" }}>
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
                minHeight: 40, padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-risk-high)",
                background: "var(--k-risk-high-bg)", color: "var(--k-risk-high)",
              }}
            >
              Reject repair
            </button>
            <button
              type="button"
              onClick={() => setRejecting(false)}
              style={{
                minHeight: 40, padding: "0 var(--k-space-4)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-border)",
                background: "transparent", color: "var(--k-text-muted)",
              }}
            >
              Back
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: "var(--k-space-2)" }}>
          <button
            type="button"
            disabled={busy || !readToEnd}
            onClick={() => void approve()}
            title={readToEnd ? "Run the proposed repair" : "Read the plan first"}
            style={{
              minHeight: 40, padding: "0 var(--k-space-4)",
              borderRadius: "var(--k-radius-md)", border: "none",
              background: "var(--k-loop-gradient)",
              color: "var(--k-text-inverse)", fontWeight: 600,
            }}
          >
            Approve repair
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setRejecting(true)}
            style={{
              minHeight: 40, padding: "0 var(--k-space-4)",
              borderRadius: "var(--k-radius-md)",
              border: "1px solid var(--k-border-strong)",
              background: "transparent", color: "var(--k-text)",
            }}
          >
            Reject
          </button>
        </div>
      )}
    </section>
  );
}

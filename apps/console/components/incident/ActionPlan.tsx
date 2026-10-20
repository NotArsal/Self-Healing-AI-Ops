/**
 * The action plan — DESIGN_SYSTEM.md §7.6.
 *
 * Action name in mono, params as a key/value grid, and the inverse directly
 * beneath prefixed `undo:`. The inverse is NEVER behind a disclosure: the
 * operator's question is "can this be undone", and the answer has to be on
 * screen.
 *
 * The risk tier shown is the one the executor already records. There is no
 * risk engine yet — P6 — so this reports a recorded value and does not compute
 * one, and the console never implies a gate evaluated it.
 *
 * Stitch refinement:
 *   - Visual impact tile with bounded blast radius and execution status
 *   - Midnight Operations tonal key-value grid
 *   - Preserves exact "undo:", "config hash", "idempotency key" dt labels
 */

import { Icon } from "../ui/Icon";
import { RiskBadge } from "../ui/pills";
import type { Action } from "@/lib/api";

const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <>
    <dt className="k-xs k-faint" style={{ fontWeight: 500, padding: "2px 0" }}>
      {label}
    </dt>
    <dd className="k-mono-sm" style={{ margin: 0, padding: "2px 0", overflowWrap: "anywhere" }}>
      {value}
    </dd>
  </>
);

const settingsText = (settings: Action["requested_settings"]): string => {
  const entries = Object.entries(settings ?? {});
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}=${String(value)}`).join(" ");
};

export function ActionPlan({
  action,
  plannedAction,
}: {
  action: Action | null;
  plannedAction: string | null;
}) {
  if (!action) {
    return (
      <div className="k-card">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="activity" size={16} />
          Repair
        </h3>
        <p className="k-sm k-muted" style={{ margin: "8px 0 0" }}>
          {plannedAction
            ? `Proposed: ${plannedAction}. Not executed.`
            : "No repair proposed."}
        </p>
      </div>
    );
  }

  return (
    <div
      className="k-card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--k-space-3)",
        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--k-space-2)",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 24,
              height: 24,
              borderRadius: "var(--k-radius-sm)",
              background: "var(--k-accent-glow)",
              color: "var(--k-accent)",
            }}
          >
            <Icon name="activity" size={14} />
          </span>
          <h3 className="k-mono" style={{ margin: 0 }}>{action.action}</h3>
        </div>
        <RiskBadge tier={action.risk_tier} />
      </header>

      {/* Stitch Blast Radius & Scope Indicator Tile */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--k-space-2)",
          padding: "var(--k-space-2) var(--k-space-3)",
          background: "var(--k-surface-sunken)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border-subtle)",
        }}
      >
        <div>
          <span className="k-xs k-faint" style={{ display: "block" }}>Blast Radius Impact</span>
          <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-risk-low)" }}>
            {action.risk_tier ? `${action.risk_tier} (Bounded)` : "—"}
          </span>
        </div>
        <div>
          <span className="k-xs k-faint" style={{ display: "block" }}>Execution Scope</span>
          <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-accent)" }}>
            {action.executed ? "Executed" : "Prepared / Staged"}
          </span>
        </div>
      </div>

      <dl
        style={{
          margin: 0,
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "4px var(--k-space-3)",
          alignItems: "baseline",
          padding: "var(--k-space-2) var(--k-space-3)",
          background: "var(--k-surface-raised)",
          borderRadius: "var(--k-radius-sm)",
          border: "1px solid var(--k-border)",
        }}
      >
        <Row label="requested" value={settingsText(action.requested_settings)} />
        <Row
          label="undo:"
          value={
            <span className="k-muted" style={{ color: "var(--k-accent)" }}>
              {settingsText(action.inverse_settings)}
            </span>
          }
        />
        <Row
          label="config hash"
          value={
            <>
              {action.config_hash_before || "—"}
              <span className="k-faint"> → </span>
              {action.config_hash_after || "—"}
            </>
          }
        />
        <Row label="idempotency key" value={action.idempotency_key || "—"} />
        <Row label="executed at" value={action.executed_at || "not executed"} />
      </dl>

      <p
        className="k-sm"
        style={{
          margin: 0,
          display: "flex",
          gap: 8,
          alignItems: "center",
          color: action.executed ? "var(--k-risk-low)" : "var(--k-text-muted)",
        }}
      >
        <Icon name={action.executed ? "check" : "pending"} />
        {action.executed
          ? "Executed, with the inverse recorded before the write"
          : "Prepared, not executed"}
        {action.error ? ` · ${action.error}` : ""}
      </p>
    </div>
  );
}

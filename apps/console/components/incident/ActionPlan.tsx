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
 */

import { Icon } from "../ui/Icon";
import { RiskBadge } from "../ui/pills";
import type { Action } from "@/lib/api";

const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <>
    <dt className="k-xs k-faint" style={{ fontWeight: 500 }}>
      {label}
    </dt>
    <dd className="k-mono-sm" style={{ margin: 0, overflowWrap: "anywhere" }}>
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
        <h3>Repair</h3>
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
      style={{ display: "flex", flexDirection: "column", gap: "var(--k-space-3)" }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--k-space-2)",
        }}
      >
        <h3 className="k-mono">{action.action}</h3>
        <RiskBadge tier={action.risk_tier} />
      </header>

      <dl
        style={{
          margin: 0,
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "4px var(--k-space-3)",
          alignItems: "baseline",
        }}
      >
        <Row label="requested" value={settingsText(action.requested_settings)} />
        <Row
          label="undo:"
          value={
            <span className="k-muted">{settingsText(action.inverse_settings)}</span>
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

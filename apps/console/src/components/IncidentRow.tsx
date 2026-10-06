import React from "react";
import { Incident } from "./types";

export function IncidentRow({
  incident,
  isActive,
  onClick,
}: {
  incident: Incident;
  isActive: boolean;
  onClick: () => void;
}) {
  const getOutcomeColor = (outcome: string) => {
    if (outcome === "RESOLVED") return "var(--color-k-success)";
    if (outcome === "MITIGATED") return "var(--color-k-caution)";
    if (outcome === "ESCALATED") return "var(--color-k-danger)";
    if (outcome === "UNRECOVERABLE") return "var(--color-k-unrecoverable)";
    return "var(--color-k-muted)";
  };

  const getOutcomeBg = (outcome: string) => {
    if (outcome === "RESOLVED") return "var(--color-k-success-bg)";
    if (outcome === "MITIGATED") return "var(--color-k-caution-bg)";
    if (outcome === "ESCALATED") return "var(--color-k-danger-bg)";
    if (outcome === "UNRECOVERABLE") return "var(--color-k-danger-bg)"; // Defaulting to danger-bg
    if (outcome === "IN_PROGRESS") return "transparent";
    return "var(--color-k-surface-strong)";
  };

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded border transition-colors bg-k-surface hover:border-k-hairline-strong ${
        isActive ? "border-k-primary shadow-sm" : "border-k-hairline"
      }`}
      aria-current={isActive ? "true" : "false"}
    >
      <div className="flex justify-between items-start mb-2">
        <span className="font-mono text-sm">{incident.id}</span>
        <span
          className="text-xs px-2 py-1 rounded font-semibold tracking-wider uppercase"
          style={{
            color: getOutcomeColor(incident.outcome),
            backgroundColor: getOutcomeBg(incident.outcome),
            border:
              incident.outcome === "IN_PROGRESS"
                ? "1px solid var(--color-k-hairline-strong)"
                : "none",
          }}
        >
          {incident.outcome}
        </span>
      </div>
      <div className="text-sm text-k-muted">
        Scenario: {incident.scenario || "Unknown"}
      </div>
      {incident.fault_class && (
        <div className="text-sm mt-1 text-k-body">
          Fault: <span className="font-mono text-k-ink">{incident.fault_class}</span>
        </div>
      )}
      {incident.outcome === "MITIGATED" && incident.debt && (
        <div className="mt-3 text-xs bg-k-caution-bg text-k-caution px-2 py-1 rounded border border-k-caution inline-block">
          Active Debt
        </div>
      )}
    </button>
  );
}

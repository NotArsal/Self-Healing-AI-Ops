/**
 * The interactive horizontal incident stage pipeline — Midnight Operations.
 *
 * Visualizes the 7 canonical healing stages in forward order:
 * 1. Detect → 2. Collect → 3. Diagnose → 4. Gate → 5. Execute → 6. Verify → 7. Resolved
 *
 * Complements the compact LoopRing with explicit labels, progression connectors,
 * textual accessibility descriptions, and a dedicated rollback unwind annotation.
 *
 * Operational rules:
 * - Reflects genuine event data; never fabricates progress.
 * - Completed, in_flight, failed, awaiting and pending states are clearly distinguished.
 * - Gate denials and failures remain visibly failed, never masked as passed.
 * - Rollback events are rendered via a dedicated status banner without corrupting
 *   forward stage definitions.
 */

"use client";

import { useMemo } from "react";

import { Icon, type IconName } from "../ui/Icon";
import type { Incident, IncidentSummary, LoopEvent } from "@/lib/api";

export type PipelineStageId =
  | "detect"
  | "collect"
  | "diagnose"
  | "gate"
  | "execute"
  | "verify"
  | "resolved";

export type StageStatus =
  | "pending"
  | "in_flight"
  | "completed"
  | "failed"
  | "awaiting";

export interface PipelineStageConfig {
  id: PipelineStageId;
  label: string;
  number: number;
  icon: IconName;
  description: string;
}

export const PIPELINE_STAGES: readonly PipelineStageConfig[] = [
  {
    id: "detect",
    label: "Detect",
    number: 1,
    icon: "activity",
    description: "Breach detection and metric anomaly recognition",
  },
  {
    id: "collect",
    label: "Collect",
    number: 2,
    icon: "list",
    description: "Evidence, config and telemetry collection",
  },
  {
    id: "diagnose",
    label: "Diagnose",
    number: 3,
    icon: "cpu",
    description: "LLM root cause analysis and fault classification",
  },
  {
    id: "gate",
    label: "Gate",
    number: 4,
    icon: "shield",
    description: "Validation checks, permit gating and human approval",
  },
  {
    id: "execute",
    label: "Execute",
    number: 5,
    icon: "gauge",
    description: "Bounded repair action execution with pre-state witness",
  },
  {
    id: "verify",
    label: "Verify",
    number: 6,
    icon: "activity",
    description: "Deterministic health and golden quality probes",
  },
  {
    id: "resolved",
    label: "Resolved",
    number: 7,
    icon: "check",
    description: "Final resolution outcome and postmortem recording",
  },
] as const;

export interface PipelineStageState {
  id: PipelineStageId;
  label: string;
  number: number;
  icon: IconName;
  status: StageStatus;
  statusLabel: string;
  detail?: string;
}

export interface RollbackState {
  active: boolean;
  status: "in_flight" | "completed" | "failed";
  statusLabel: string;
  message?: string;
}

export interface PipelineCalculationResult {
  stages: PipelineStageState[];
  rollback: RollbackState | null;
  activeStageId: PipelineStageId | null;
}

/**
 * Derives the pipeline state from real incident events and incident metadata.
 */
export function calculatePipelineStages(
  events: LoopEvent[],
  incidentId?: string,
  incident?: Incident | IncidentSummary | null,
  busy?: boolean,
): PipelineCalculationResult {
  const scopedEvents = incidentId
    ? events.filter((e) => !e.incident_id || e.incident_id === incidentId)
    : events;

  let detectStatus: StageStatus = "pending";
  let collectStatus: StageStatus = "pending";
  let diagnoseStatus: StageStatus = "pending";
  let gateStatus: StageStatus = "pending";
  let executeStatus: StageStatus = "pending";
  let verifyStatus: StageStatus = "pending";
  let resolvedStatus: StageStatus = "pending";

  let detectMsg = "";
  let collectMsg = "";
  let diagnoseMsg = "";
  let gateMsg = "";
  let executeMsg = "";
  let verifyMsg = "";
  let resolveMsg = "";

  let rollback: RollbackState | null = null;
  let activeStageId: PipelineStageId | null = null;

  for (const event of scopedEvents) {
    const stage = event.stage.toLowerCase();
    const status = event.status.toLowerCase();

    // 1. Detect
    if (stage === "detect") {
      if (status === "failed") {
        detectStatus = "failed";
        detectMsg = event.message;
        if (activeStageId === "detect") activeStageId = null;
      } else if (status === "ok") {
        detectStatus = "completed";
        detectMsg = event.message;
        if (activeStageId === "detect") activeStageId = null;
      } else if (status === "started") {
        detectStatus = "in_flight";
        detectMsg = event.message;
        activeStageId = "detect";
      }
    } else if (stage === "run" && status === "started" && detectStatus === "pending") {
      detectStatus = "in_flight";
      activeStageId = "detect";
    }

    // 2. Collect (evidence gathering)
    if (stage === "evidence" || stage === "collect") {
      if (status === "failed") {
        collectStatus = "failed";
        collectMsg = event.message;
        if (activeStageId === "collect") activeStageId = null;
      } else if (status === "ok") {
        collectStatus = "completed";
        collectMsg = event.message;
        if (activeStageId === "collect") activeStageId = null;
      } else if (status === "started") {
        collectStatus = "in_flight";
        collectMsg = event.message;
        activeStageId = "collect";
      }
    }

    // 3. Diagnose
    if (stage === "diagnose") {
      if (status === "failed") {
        diagnoseStatus = "failed";
        diagnoseMsg = event.message;
        if (activeStageId === "diagnose") activeStageId = null;
      } else if (status === "ok") {
        diagnoseStatus = "completed";
        diagnoseMsg = event.message;
        if (activeStageId === "diagnose") activeStageId = null;
      } else if (status === "started") {
        diagnoseStatus = "in_flight";
        diagnoseMsg = event.message;
        activeStageId = "diagnose";
      }
    }

    // 4. Gate (validate, plan, and permit checks)
    if (stage === "validate" || stage === "gate" || stage === "plan") {
      if (status === "failed") {
        gateStatus = "failed";
        gateMsg = event.message;
        if (activeStageId === "gate") activeStageId = null;
      } else if (status === "ok") {
        if (stage === "gate") {
          gateStatus = "completed";
          gateMsg = event.message;
          if (activeStageId === "gate") activeStageId = null;
        } else if (stage === "validate" && gateStatus !== "failed") {
          if (gateStatus === "pending") gateStatus = "in_flight";
          gateMsg = event.message;
        } else if (stage === "plan" && gateStatus === "pending") {
          gateStatus = "in_flight";
          gateMsg = event.message;
        }
      } else if (status === "started") {
        gateStatus = "in_flight";
        gateMsg = event.message;
        activeStageId = "gate";
      }
    }

    // 5. Execute (repair writes)
    if (stage === "repair" || stage === "execute") {
      if (status === "failed") {
        executeStatus = "failed";
        executeMsg = event.message;
        if (activeStageId === "execute") activeStageId = null;
      } else if (status === "ok") {
        executeStatus = "completed";
        executeMsg = event.message;
        if (activeStageId === "execute") activeStageId = null;
      } else if (status === "started") {
        executeStatus = "in_flight";
        executeMsg = event.message;
        activeStageId = "execute";
      }
    }

    // 6. Verify (probes)
    if (stage === "verify") {
      if (status === "failed") {
        verifyStatus = "failed";
        verifyMsg = event.message;
        if (activeStageId === "verify") activeStageId = null;
      } else if (status === "ok") {
        verifyStatus = "completed";
        verifyMsg = event.message;
        if (activeStageId === "verify") activeStageId = null;
      } else if (status === "started") {
        verifyStatus = "in_flight";
        verifyMsg = event.message;
        activeStageId = "verify";
      }
    }

    // Rollback event handling — distinct from forward stages
    if (stage === "rollback") {
      if (status === "started") {
        rollback = {
          active: true,
          status: "in_flight",
          statusLabel: "Active",
          message: event.message,
        };
      } else if (status === "ok") {
        rollback = {
          active: true,
          status: "completed",
          statusLabel: "Rolled back",
          message: event.message,
        };
      } else if (status === "failed") {
        rollback = {
          active: true,
          status: "failed",
          statusLabel: "Failed",
          message: event.message,
        };
      }
    }

    // 7. Resolved
    if (stage === "resolve") {
      if (status === "ok") {
        resolvedStatus = "completed";
        resolveMsg = event.message;
        if (activeStageId === "resolved") activeStageId = null;
      } else if (status === "failed") {
        resolvedStatus = "failed";
        resolveMsg = event.message;
        if (activeStageId === "resolved") activeStageId = null;
      } else if (status === "started") {
        resolvedStatus = "in_flight";
        resolveMsg = event.message;
        activeStageId = "resolved";
      }
    }
  }

  // Correlate with incident object state if present
  if (incident) {
    const incStatus = incident.status;
    const isAwaiting =
      Boolean((incident as Incident).awaiting_approval) ||
      incStatus === "AWAITING" ||
      incStatus === "AWAITING_APPROVAL";

    if (isAwaiting && gateStatus !== "completed" && gateStatus !== "failed") {
      gateStatus = "awaiting";
      gateMsg = "Awaiting operator authorization";
      activeStageId = "gate";
    }

    if (incStatus === "RESOLVED") {
      resolvedStatus = "completed";
      if (!resolveMsg && (incident as IncidentSummary).outcome) {
        resolveMsg = (incident as IncidentSummary).outcome;
      }
    } else if (incStatus === "ESCALATED") {
      resolvedStatus = "failed";
      if (!resolveMsg) resolveMsg = (incident as Incident).escalation_reason || "Escalated";
    } else if (incStatus === "ROLLED_BACK") {
      if (!rollback) {
        rollback = {
          active: true,
          status: "completed",
          statusLabel: "Rolled back",
          message: "Unwound actions to prior verified state",
        };
      }
    } else if (incStatus === "NO_FAULT") {
      detectStatus = "completed";
      resolvedStatus = "completed";
      resolveMsg = "No fault detected";
    }
  }

  // If busy is false and no operation running, clear in-flight active highlight
  if (busy === false && activeStageId) {
    activeStageId = null;
  }

  const statusLabelFor = (status: StageStatus): string => {
    switch (status) {
      case "completed":
        return "Passed";
      case "in_flight":
        return "Running";
      case "failed":
        return "Failed";
      case "awaiting":
        return "Awaiting approval";
      case "pending":
      default:
        return "Pending";
    }
  };

  const stageMessages: Record<PipelineStageId, string | undefined> = {
    detect: detectMsg || undefined,
    collect: collectMsg || undefined,
    diagnose: diagnoseMsg || undefined,
    gate: gateMsg || undefined,
    execute: executeMsg || undefined,
    verify: verifyMsg || undefined,
    resolved: resolveMsg || undefined,
  };

  const statuses: Record<PipelineStageId, StageStatus> = {
    detect: detectStatus,
    collect: collectStatus,
    diagnose: diagnoseStatus,
    gate: gateStatus,
    execute: executeStatus,
    verify: verifyStatus,
    resolved: resolvedStatus,
  };

  const stages: PipelineStageState[] = PIPELINE_STAGES.map((cfg) => {
    const s = statuses[cfg.id];
    return {
      ...cfg,
      status: s,
      statusLabel: statusLabelFor(s),
      detail: stageMessages[cfg.id],
    };
  });

  return { stages, rollback, activeStageId };
}

export function LoopStageBar({
  events,
  incidentId,
  incident,
  busy = false,
}: {
  events: LoopEvent[];
  incidentId?: string;
  incident?: Incident | IncidentSummary | null;
  busy?: boolean;
}) {
  const { stages, rollback, activeStageId } = useMemo(
    () => calculatePipelineStages(events, incidentId, incident, busy),
    [events, incidentId, incident, busy],
  );

  return (
    <nav
      aria-label="Incident healing pipeline"
      className="k-panel"
      style={{
        padding: "var(--k-space-3) var(--k-space-4)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--k-space-2)",
        background: "var(--k-surface)",
        border: "1px solid var(--k-border)",
        borderRadius: "var(--k-radius-md)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--k-space-2)",
          marginBottom: 2,
        }}
      >
        <span
          className="k-xs"
          style={{
            fontWeight: 600,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color: "var(--k-text-muted)",
          }}
        >
          Healing Lifecycle
        </span>
        <span className="k-mono-sm k-faint" style={{ fontSize: 11 }}>
          {stages.filter((s) => s.status === "completed").length} of {stages.length} stages reached
        </span>
      </div>

      {/* Horizontal Stage Stepper */}
      <ol
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "grid",
          gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
          gap: "var(--k-space-2)",
          alignItems: "center",
        }}
      >
        {stages.map((stage, idx) => {
          const isCompleted = stage.status === "completed";
          const isInFlight = stage.status === "in_flight" || activeStageId === stage.id;
          const isFailed = stage.status === "failed";
          const isAwaiting = stage.status === "awaiting";

          let badgeBorder = "var(--k-border)";
          let badgeBg = "var(--k-surface-sunken)";
          let badgeColor = "var(--k-text-faint)";
          let iconName: IconName = stage.icon;

          if (isCompleted) {
            badgeBorder = "var(--k-risk-low)";
            badgeBg = "var(--k-risk-low-bg)";
            badgeColor = "var(--k-risk-low)";
            iconName = "check";
          } else if (isInFlight) {
            badgeBorder = "var(--k-state-healing)";
            badgeBg = "var(--k-surface-raised)";
            badgeColor = "var(--k-state-healing)";
            iconName = "pending";
          } else if (isFailed) {
            badgeBorder = "var(--k-risk-high)";
            badgeBg = "var(--k-risk-high-bg)";
            badgeColor = "var(--k-risk-high)";
            iconName = "cross";
          } else if (isAwaiting) {
            badgeBorder = "var(--k-risk-med)";
            badgeBg = "var(--k-risk-med-bg)";
            badgeColor = "var(--k-risk-med)";
            iconName = "shield-alert";
          }

          return (
            <li
              key={stage.id}
              tabIndex={0}
              aria-current={isInFlight ? "step" : undefined}
              aria-label={`${stage.number}. ${stage.label}: ${stage.statusLabel}`}
              title={stage.detail || `${stage.label}: ${stage.statusLabel}`}
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
                padding: "4px 2px",
                borderRadius: "var(--k-radius-sm)",
                transition: "all var(--k-dur-base) var(--k-ease)",
                cursor: "default",
                outline: "none",
              }}
            >
              {/* Connector line to next stage */}
              {idx < stages.length - 1 && (
                <span
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    top: 18,
                    left: "calc(50% + 14px)",
                    right: "calc(-50% + 14px)",
                    height: 2,
                    background: isCompleted
                      ? "var(--k-risk-low)"
                      : isInFlight
                        ? "linear-gradient(90deg, var(--k-state-healing), var(--k-border))"
                        : "var(--k-border-subtle)",
                    zIndex: 0,
                    transition: "background var(--k-dur-base) var(--k-ease)",
                  }}
                />
              )}

              {/* Stage Marker Badge */}
              <div
                style={{
                  position: "relative",
                  zIndex: 1,
                  width: 28,
                  height: 28,
                  borderRadius: "var(--k-radius-full)",
                  background: badgeBg,
                  border: `1px solid ${badgeBorder}`,
                  color: badgeColor,
                  display: "grid",
                  placeItems: "center",
                  boxShadow: isInFlight ? "var(--k-glow-subtle)" : undefined,
                  transition: "all var(--k-dur-base) var(--k-ease)",
                }}
              >
                <Icon name={iconName} size={13} />
              </div>

              {/* Stage Label & Status */}
              <div style={{ marginTop: 6, minWidth: 0, maxWidth: "100%" }}>
                <span
                  style={{
                    display: "block",
                    fontSize: 12,
                    fontWeight: isInFlight || isCompleted ? 600 : 500,
                    color: isInFlight
                      ? "var(--k-state-healing)"
                      : isFailed
                        ? "var(--k-risk-high)"
                        : isAwaiting
                          ? "var(--k-risk-med)"
                          : isCompleted
                            ? "var(--k-text)"
                            : "var(--k-text-muted)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {stage.label}
                </span>

                <span
                  className="k-mono-sm"
                  style={{
                    display: "block",
                    fontSize: 10,
                    lineHeight: "14px",
                    color: isCompleted
                      ? "var(--k-risk-low)"
                      : isFailed
                        ? "var(--k-risk-high)"
                        : isAwaiting
                          ? "var(--k-risk-med)"
                          : isInFlight
                            ? "var(--k-state-healing)"
                            : "var(--k-text-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {stage.statusLabel}
                </span>
                <span className="k-sr-only">. Status: {stage.statusLabel}.</span>
              </div>
            </li>
          );
        })}
      </ol>

      {/* Rollback Notification Banner — Distinct from forward stages */}
      {rollback && rollback.active && (
        <div
          role="status"
          aria-label="Rollback event"
          style={{
            marginTop: "var(--k-space-2)",
            padding: "var(--k-space-2) var(--k-space-3)",
            borderRadius: "var(--k-radius-sm)",
            border: `1px solid ${
              rollback.status === "failed" ? "var(--k-risk-high)" : "var(--k-state-rolledback)"
            }`,
            background:
              rollback.status === "failed" ? "var(--k-risk-high-bg)" : "rgba(245, 138, 71, 0.12)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--k-space-2)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span
              style={{
                color:
                  rollback.status === "failed"
                    ? "var(--k-risk-high)"
                    : "var(--k-state-rolledback)",
                display: "flex",
              }}
            >
              <Icon name="shield-alert" size={14} />
            </span>
            <span
              style={{
                fontWeight: 600,
                color:
                  rollback.status === "failed"
                    ? "var(--k-risk-high)"
                    : "var(--k-state-rolledback)",
                fontSize: 12,
              }}
            >
              Rollback {rollback.statusLabel.toLowerCase()}
            </span>
            {rollback.message && (
              <span
                className="k-mono-sm"
                style={{
                  color: "var(--k-text)",
                  fontSize: 11,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                — {rollback.message}
              </span>
            )}
          </div>
          <span
            className="k-xs"
            style={{
              padding: "2px 8px",
              borderRadius: "var(--k-radius-sm)",
              background: "var(--k-surface)",
              color:
                rollback.status === "failed"
                  ? "var(--k-risk-high)"
                  : "var(--k-state-rolledback)",
              fontWeight: 500,
              fontSize: 11,
              flexShrink: 0,
            }}
          >
            Unwind
          </span>
        </div>
      )}
    </nav>
  );
}

/**
 * The operations screen — three zones, DESIGN_SYSTEM.md §6.
 *
 *   left 64px rail   navigation, theme, mode indicator (never scrolls away)
 *   left panel       project identity and dependency health
 *   centre           active incident, Loop Ring and the live timeline
 *   right 380px      inspector in fixed loop order: evidence -> diagnosis
 *                    -> plan -> verification
 *
 * The inspector order never changes, because the operator learns the position.
 *
 * Sized for 1280x720: the whole thing is one viewport-height grid with its own
 * scroll regions, so the active incident and the timeline dominate the screen
 * during a live demo and nothing important needs page scrolling.
 */

"use client";

import { useEffect, useMemo, useState } from "react";

import { ActionPlan } from "@/components/incident/ActionPlan";
import { DiagnosisCard } from "@/components/incident/DiagnosisCard";
import { EvidenceList } from "@/components/incident/EvidenceList";
import {
  HistoryTable,
  IncidentStream,
  reachedStages,
} from "@/components/incident/IncidentStream";
import { LoopRing } from "@/components/incident/LoopRing";
import { LoopStageBar } from "@/components/incident/LoopStageBar";
import { Timeline } from "@/components/incident/Timeline";
import { ApprovalPanel } from "@/components/safety/ApprovalPanel";
import { ModeSwitch } from "@/components/safety/ModeSwitch";
import { SystemHealth } from "@/components/safety/SystemHealth";
import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { StatePill } from "@/components/ui/pills";
import { VerificationStrip } from "@/components/incident/VerificationStrip";
import { api } from "@/lib/api";
import { useEvents, useIncidents, useSafetyState, useSystem } from "@/lib/live";

const TERMINAL = new Set(["RESOLVED", "ESCALATED", "NO_FAULT"]);

export default function OperationsPage() {
  const { system, error, refresh: refreshSystem } = useSystem();
  const { mode, metrics, setMode, refresh: refreshSafety } = useSafetyState();
  const { events, connected } = useEvents();
  const [selectedId, setSelectedId] = useState("");
  const { incidents, selected, refresh } = useIncidents(selectedId);
  const [openEvidence, setOpenEvidence] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  // Follow whatever the control plane says is running, and otherwise the
  // newest incident, so the demo needs no clicking to land on the right row.
  useEffect(() => {
    const running = system?.running_incident_id;
    if (running && running !== selectedId) {
      setSelectedId(running);
      return;
    }
    if (!selectedId && incidents.length > 0) {
      setSelectedId(incidents[0]?.incident_id ?? "");
    }
  }, [system?.running_incident_id, incidents, selectedId]);

  // Refetch the incident when a stage finishes: the socket carries progress
  // lines, the REST detail carries the structured record the cards render.
  const lastSeq = events.at(-1)?.seq ?? 0;
  useEffect(() => {
    if (lastSeq > 0) {
      refresh();
      refreshSystem();
      refreshSafety();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastSeq]);

  const ring = useMemo(
    () => reachedStages(events, selectedId),
    [events, selectedId],
  );

  const scopedEvents = useMemo(
    () =>
      selectedId
        ? events.filter((e) => !e.incident_id || e.incident_id === selectedId)
        : events,
    [events, selectedId],
  );

  const run = async (): Promise<void> => {
    setStarting(true);
    setStartError("");
    const { data, error: err, response } = await api.POST("/v1/loop/run", {
      params: { query: { rca: true } },
    });
    setStarting(false);
    if (err || !data) {
      setStartError(
        response?.status === 409
          ? "A loop run is already in flight. One writer at a time."
          : response?.status === 412
            ? "No baseline capture on disk. Run `make onboard` against a healthy target first."
            : "Could not start a run. Is the control plane up?",
      );
      return;
    }
    setSelectedId(data.incident_id);
    refresh();
  };

  const busy = Boolean(system?.loop_running) || starting;
  const evidence = selected?.rca?.evidence ?? [];
  const cited = selected?.rca?.diagnosis?.evidence_ids ?? [];

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail
        mode={system?.mode ?? "SIMULATION"}
        modeEnforced={system?.mode_is_enforced ?? false}
        current="/"
      />

      <div className="k-zones">
        {/* left: where */}
        <aside
          className="k-scroll"
          aria-label="System health"
          style={{ minWidth: 0 }}
        >
          <SystemHealth system={system} error={error} metrics={metrics} />
          <div style={{ marginTop: "var(--k-space-4)" }}>
            <ModeSwitch
              state={mode}
              onChanged={(next) => {
                setMode(next);
                refreshSystem();
              }}
            />
          </div>
        </aside>

        {/* centre: what */}
        <main
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--k-space-4)",
            minWidth: 0,
            minHeight: 0,
          }}
        >
          <header
            className="k-panel"
            style={{
              padding: "var(--k-space-4)",
              display: "flex",
              flexDirection: "column",
              gap: "var(--k-space-3)",
              borderTop: busy ? "2px solid transparent" : undefined,
              backgroundImage: busy
                ? "linear-gradient(var(--k-surface), var(--k-surface)), var(--k-loop-gradient)"
                : undefined,
              backgroundOrigin: busy ? "border-box" : undefined,
              backgroundClip: busy ? "padding-box, border-box" : undefined,
            }}
          >
            {/* Stitch-guided Top Banner Status Bar when incident active */}
            {selected && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "var(--k-space-2)",
                  paddingBottom: "var(--k-space-2)",
                  borderBottom: "1px solid var(--k-border-subtle)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span
                    className="k-mono-sm"
                    style={{
                      padding: "2px 8px",
                      borderRadius: "var(--k-radius-sm)",
                      background: selected.status === "ESCALATED" ? "var(--k-risk-high-bg)" : "var(--k-surface-raised)",
                      border: `1px solid ${selected.status === "ESCALATED" ? "var(--k-risk-high)" : "var(--k-border)"}`,
                      color: selected.status === "ESCALATED" ? "var(--k-risk-high)" : "var(--k-text)",
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: "uppercase",
                    }}
                  >
                    {(selected.decision?.risk_tier ?? selected.action?.risk_tier) ? `TIER: ${selected.decision?.risk_tier ?? selected.action?.risk_tier}` : "INCIDENT ACTIVE"}
                  </span>
                  <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-text)" }}>
                    #{selected.incident_id}
                  </span>
                  {selected.service && (
                    <span className="k-mono-sm k-muted" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      · <Icon name="cpu" size={13} /> {selected.service}
                    </span>
                  )}
                  {selected.detected_at && (
                    <span className="k-mono-sm k-faint">
                      · detected {selected.detected_at.slice(11, 19)} UTC
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {selected.awaiting_approval && (
                    <span
                      className="k-mono-sm"
                      style={{
                        padding: "2px 8px",
                        borderRadius: "var(--k-radius-sm)",
                        background: "var(--k-risk-med-bg)",
                        border: "1px solid var(--k-risk-med)",
                        color: "var(--k-risk-med)",
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                    >
                      GATED AT STEP 4
                    </span>
                  )}
                  <span
                    className="k-mono-sm"
                    style={{
                      padding: "2px 8px",
                      borderRadius: "var(--k-radius-sm)",
                      background: "var(--k-surface-sunken)",
                      border: "1px solid var(--k-border)",
                      color: "var(--k-text-muted)",
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    MODE: {system?.mode ?? "SIMULATION"}
                  </span>
                </div>
              </div>
            )}

            {/* Core Header Row */}
            <div style={{ display: "flex", gap: "var(--k-space-4)", alignItems: "center" }}>
              <LoopRing
                reached={ring.reached}
                failed={ring.failed}
                inFlight={ring.inFlight && busy}
                size={72}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <h1 style={{ display: "flex", alignItems: "baseline", gap: 10, margin: 0 }}>
                  {selected?.fault_class ? (
                    <>
                      <span className="k-mono">{selected.fault_class}</span>
                      <span>{(selected.fault_name ?? "").replace(/_/g, " ")}</span>
                    </>
                  ) : (
                    "No active incident"
                  )}
                </h1>
                <p className="k-mono-sm k-faint" style={{ margin: "4px 0 0" }}>
                  {selected ? (
                    <>
                      {selected.incident_id}
                      {selected.service ? ` · ${selected.service}` : ""}
                      {selected.detected_at
                        ? ` · detected ${selected.detected_at.slice(11, 19)}`
                        : ""}
                      {selected.diagnosed_by ? ` · ${selected.diagnosed_by}` : ""}
                    </>
                  ) : (
                    "Inject F06, then start a run to watch the loop"
                  )}
                </p>
              </div>
              {selected && <StatePill status={selected.status} />}
              <button
                type="button"
                onClick={() => void run()}
                disabled={busy}
                title={
                  busy
                    ? "A loop run is already in flight. One writer at a time."
                    : "Run one pass of detect, diagnose, validate, repair and verify"
                }
                style={{
                  minHeight: 40,
                  padding: "0 var(--k-space-4)",
                  borderRadius: "var(--k-radius-md)",
                  border: "none",
                  background: "var(--k-loop-gradient)",
                  color: "var(--k-text-inverse)",
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: busy ? "default" : "pointer",
                }}
              >
                <Icon name={busy ? "pending" : "activity"} size={15} />
                {busy ? "Running" : "Run loop"}
              </button>
            </div>

            {/* Quick Incident Metadata Strip when incident active */}
            {selected && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                  gap: "var(--k-space-2)",
                  padding: "var(--k-space-2) var(--k-space-3)",
                  background: "var(--k-surface-sunken)",
                  borderRadius: "var(--k-radius-sm)",
                  border: "1px solid var(--k-border-subtle)",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <span className="k-xs k-faint">Orchestrator</span>
                  <span className="k-mono-sm" style={{ fontWeight: 600 }}>
                    {selected.diagnosed_by || "Autonomous Loop"}
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <span className="k-xs k-faint">Fault Class</span>
                  <span className="k-mono-sm" style={{ fontWeight: 600 }}>
                    {selected.fault_class || "—"}
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <span className="k-xs k-faint">Trigger</span>
                  <span className="k-mono-sm" style={{ fontWeight: 600 }}>
                    {selected.detection?.verdict || "telemetry anomaly"}
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <span className="k-xs k-faint">Lifecycle Outcome</span>
                  <span className="k-mono-sm" style={{ fontWeight: 600, color: "var(--k-text-muted)" }}>
                    {selected.outcome || selected.status}
                  </span>
                </div>
              </div>
            )}
          </header>

          {startError && (
            <p
              role="alert"
              className="k-sm"
              style={{
                margin: 0,
                padding: "var(--k-space-3)",
                borderRadius: "var(--k-radius-md)",
                border: "1px solid var(--k-risk-high)",
                background: "var(--k-risk-high-bg)",
                color: "var(--k-risk-high)",
              }}
            >
              {startError}
            </p>
          )}

          <LoopStageBar
            events={scopedEvents}
            incidentId={selectedId}
            incident={selected}
            busy={busy}
          />

          <div
            className="k-panel"
            style={{
              padding: "var(--k-space-4)",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
              flex: 1,
            }}
          >
            <Timeline events={scopedEvents} connected={connected} />
          </div>

          <div className="k-scroll" style={{ maxHeight: 220 }}>
            <IncidentStream
              incidents={incidents}
              selectedId={selectedId}
              onSelect={setSelectedId}
              events={events}
            />
            <HistoryTable incidents={incidents} />
          </div>
        </main>

        {/* right: why. Order is fixed and never changes. */}
        <aside
          className="k-scroll"
          aria-label="Inspector"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--k-space-4)",
            minWidth: 0,
          }}
        >
          {selected?.awaiting_approval && (
            <ApprovalPanel
              incident={selected}
              onDecided={() => {
                refresh();
                refreshSystem();
                refreshSafety();
              }}
            />
          )}
          <EvidenceList
            items={evidence}
            citedIds={cited}
            openId={openEvidence}
            onOpenChange={setOpenEvidence}
          />
          <DiagnosisCard
            rca={selected?.rca ?? null}
            onCitationClick={setOpenEvidence}
          />
          <ActionPlan
            action={selected?.action ?? null}
            plannedAction={selected?.planned_action ?? null}
          />
          <VerificationStrip
            verification={selected?.verification ?? null}
            incident={
              selected && TERMINAL.has(selected.status) ? selected : (selected ?? null)
            }
          />
        </aside>
      </div>
    </div>
  );
}
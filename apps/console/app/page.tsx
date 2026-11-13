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
import Link from "next/link";

import { IncidentStream, reachedStages } from "@/components/incident/IncidentStream";
import { LoopRing } from "@/components/incident/LoopRing";
import { Timeline } from "@/components/incident/Timeline";
import { ApprovalPanel } from "@/components/safety/ApprovalPanel";
import { ModeSwitch } from "@/components/safety/ModeSwitch";
import { SystemHealth } from "@/components/safety/SystemHealth";
import { Icon } from "@/components/ui/Icon";
import { Rail } from "@/components/ui/Rail";
import { StatePill } from "@/components/ui/pills";
import { VerificationStrip } from "@/components/incident/VerificationStrip";
import { api } from "@/lib/api";
import { faultName } from "@/lib/faults";
import {
  mergeEvents,
  useEvents,
  useIncidents,
  useSafetyState,
  useStoredEvents,
  useSystem,
} from "@/lib/live";

// The newest few. Everything else is on the History page (ADR 0029): the
// full table used to sit under this list, 3654px down a 210px box.
const STREAM_MAX = 8;

const ONE_LINE: React.CSSProperties = {
  minWidth: 0,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

export default function OperationsPage() {
  const { system, error, refresh: refreshSystem } = useSystem();
  const { mode, metrics, setMode, refresh: refreshSafety } = useSafetyState();
  const { events, connected } = useEvents();
  const [selectedId, setSelectedId] = useState("");
  const { incidents, loaded, selected, refresh } = useIncidents(selectedId);
  const [openEvidence, setOpenEvidence] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  // The History page links here with ?incident=<id>. Read once, on arrival.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("incident");
    if (wanted) setSelectedId(wanted);
  }, []);

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

  // Stored as well as live, so a past incident keeps its timeline and its
  // ring after the API restarts.
  const storedEvents = useStoredEvents(selectedId);
  const scopedEvents = useMemo(
    () =>
      selectedId
        ? mergeEvents(
            storedEvents,
            events.filter((e) => !e.incident_id || e.incident_id === selectedId),
          )
        : events,
    [events, storedEvents, selectedId],
  );

  const ring = useMemo(
    () => reachedStages(scopedEvents, selectedId),
    [scopedEvents, selectedId],
  );

  const run = async (): Promise<void> => {
    setStarting(true);
    setStartError("");
    // try/finally: `api.POST` REJECTS when the control plane is down, and the
    // plain `setStarting(false)` after the await never ran - the button read
    // "Running" and stayed disabled until the page was reloaded.
    try {
      const { data, error: err, response } = await api.POST("/v1/loop/run", {
        params: { query: { rca: true } },
      });
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
    } catch {
      setStartError("Could not start a run. Is the control plane up?");
    } finally {
      setStarting(false);
    }
  };

  const busy = Boolean(system?.loop_running) || starting;
  // "No active incident" only when nothing is selected. A selected incident
  // with no class (nothing found, or not enough evidence) said the same,
  // which read as if the selection had not happened.
  const title = selected?.fault_class
    ? `${selected.fault_class} ${faultName(selected.fault_class, selected.fault_name)}`
    : selected
      ? "No fault class"
      : "No active incident";
  const meta = selected
    ? [
        selected.incident_id,
        selected.service,
        selected.detected_at && `detected ${selected.detected_at.slice(11, 19)}`,
        selected.diagnosed_by,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
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
              gap: "var(--k-space-4)",
              alignItems: "center",
              // The 2px gradient top border is permitted only on the active
              // incident panel (§2.4).
              borderTop: busy ? "2px solid transparent" : undefined,
              backgroundImage: busy
                ? "linear-gradient(var(--k-surface), var(--k-surface)), var(--k-loop-gradient)"
                : undefined,
              backgroundOrigin: busy ? "border-box" : undefined,
              backgroundClip: busy ? "padding-box, border-box" : undefined,
            }}
          >
            <LoopRing
              reached={ring.reached}
              failed={ring.failed}
              inFlight={ring.inFlight && busy}
              size={72}
            />
            {/* One line each, so the header stays one ring tall at 1280x720.
                It wrapped to 156px, a fifth of the projector's height. The
                pill sits on the meta line to give the title the width. */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <h1 title={title} style={ONE_LINE}>
                {selected?.fault_class ? (
                  <>
                    <span className="k-mono">{selected.fault_class}</span>{" "}
                    {faultName(selected.fault_class, selected.fault_name)}
                  </>
                ) : (
                  title
                )}
              </h1>
              {selected ? (
                <div
                  style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}
                >
                  <StatePill status={selected.status} />
                  <p className="k-mono-sm k-faint" title={meta} style={{ ...ONE_LINE, margin: 0 }}>
                    {meta}
                  </p>
                </div>
              ) : (
                <p className="k-mono-sm k-faint" style={{ margin: "4px 0 0" }}>
                  Inject F06, then start a run to watch the loop
                </p>
              )}
            </div>
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
              }}
            >
              <Icon name={busy ? "pending" : "activity"} size={15} />
              {busy ? "Running" : "Run loop"}
            </button>
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
              incidents={incidents.slice(0, STREAM_MAX)}
              selectedId={selectedId}
              onSelect={setSelectedId}
              events={events}
              loading={!loaded}
            />
            {incidents.length > STREAM_MAX && (
              <p className="k-sm" style={{ margin: "var(--k-space-2) 0 0" }}>
                <Link href="/history">Open the full history</Link>
                <span className="k-faint">
                  {" "}
                  · the newest {STREAM_MAX} are listed here
                </span>
              </p>
            )}
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
            incident={selected}
          />
        </aside>
      </div>
    </div>
  );
}

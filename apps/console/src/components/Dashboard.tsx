"use client";

import { useState, useEffect } from "react";
import { Incident } from "./types";
import { LoopTimeline } from "./LoopTimeline";
import { IncidentRow } from "./IncidentRow";
import { DeltaStrip } from "./DeltaStrip";
import { DiagnosisCard } from "./DiagnosisCard";
import { ActionPlan } from "./ActionPlan";
import { UndoStackTimeline } from "./UndoStackTimeline";
import { TopologyGraph } from "./TopologyGraph";

export function Dashboard() {
  const [incidents, setIncidents] = useState<Record<string, Incident>>({});
  const [activeIncident, setActiveIncident] = useState<Incident | null>(null);

  useEffect(() => {
    // Fetch initial list
    fetch("http://localhost:8000/incidents")
      .then((res) => res.json())
      .then((data) => setIncidents(data))
      .catch((err) => console.error(err));

    // Listen to SSE
    const evtSource = new EventSource("http://localhost:8000/events/stream");
    evtSource.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (
        payload.type === "incident_created" ||
        payload.type === "node_completed"
      ) {
        const incId = payload.incident_id;

        // Update local list
        setIncidents((prev) => ({
          ...prev,
          [incId]: {
            ...prev[incId],
            scenario: payload.scenario || prev[incId]?.scenario,
            outcome: payload.state?.outcome || "IN_PROGRESS",
            fault_class: payload.state?.fault_class,
            gate_verdict: payload.state?.gate_verdict,
            gate_reason: payload.state?.gate_reason,
          },
        }));

        // If this is the active incident, refetch details to keep UI updated
        setActiveIncident((prev) => {
          if (prev && prev.id === incId) {
            fetchIncident(incId);
          }
          return prev;
        });
      }
    };

    return () => {
      evtSource.close();
    };
  }, []);

  const fetchIncident = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/incidents/${id}`);
      const data = await res.json();
      setActiveIncident({ id, ...data });
    } catch (e) {
      console.error(e);
    }
  };

  const launchScenario = async (name: string) => {
    try {
      const res = await fetch("http://localhost:8000/incidents/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: name }),
      });
      const data = await res.json();
      fetchIncident(data.incident_id);
    } catch (e) {
      console.error(e);
    }
  };

  const repayDebt = async (id: string) => {
    try {
      await fetch(`http://localhost:8000/incidents/${id}/repay-debt`, {
        method: "POST",
      });
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-k-canvas text-k-ink">
      <header className="h-16 px-6 flex items-center border-b border-k-hairline bg-k-surface">
        <h1 className="text-xl font-semibold tracking-tight text-k-primary">
          Kavach
        </h1>
        <div className="ml-auto flex items-center gap-2">
          {["F01", "F02", "F03", "F04", "F05"].map((f) => (
            <button
              key={f}
              onClick={() => launchScenario(f)}
              className="px-3 py-1 bg-k-surface text-k-ink border border-k-hairline-strong rounded hover:border-k-ink text-xs font-medium transition-colors"
            >
              Launch {f}
            </button>
          ))}
          <span className="ml-4 text-[10px] px-2 py-1 bg-k-surface-strong rounded text-k-ink uppercase tracking-wider font-bold border border-k-hairline">
            SIMULATION
          </span>
        </div>
      </header>

      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-8 max-w-[1440px] mx-auto w-full">
        {/* Stream */}
        <section className="flex flex-col gap-6" aria-label="Incident Stream">
          <h2 className="text-2xl font-medium tracking-tight">
            Active Incidents
          </h2>
          <div className="flex flex-col gap-3">
            {Object.keys(incidents).length === 0 ? (
              <div className="text-k-muted text-sm bg-k-canvas-soft p-8 rounded border border-k-hairline text-center">
                No incidents. Launch a scenario to begin.
              </div>
            ) : (
              Object.entries(incidents)
                .reverse()
                .map(([id, inc]) => (
                  <IncidentRow
                    key={id}
                    incident={inc}
                    isActive={activeIncident?.id === id}
                    onClick={() => fetchIncident(id)}
                  />
                ))
            )}
          </div>
        </section>

        {/* Inspector */}
        <aside className="flex flex-col gap-6" aria-label="Incident Inspector">
          <h2 className="text-2xl font-medium tracking-tight">Inspector</h2>
          {!activeIncident ? (
            <div className="text-k-muted text-sm bg-k-canvas-soft p-8 rounded border border-k-hairline text-center flex flex-col items-center justify-center min-h-[400px]">
              Select an incident to view details.
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              <LoopTimeline currentStage="detect" />

              <div className="bg-k-surface rounded border border-k-hairline p-5 shadow-sm">
                <h3 className="font-semibold mb-4 text-[11px] uppercase tracking-wider text-k-muted border-b border-k-hairline pb-2">
                  LLM Diagnosis
                </h3>
                <DiagnosisCard diagnosis={activeIncident.diagnosis} />
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-5 shadow-sm">
                <h3 className="font-semibold mb-4 text-[11px] uppercase tracking-wider text-k-muted border-b border-k-hairline pb-2">
                  Safety Gate (TNR)
                </h3>
                {activeIncident.gate_verdict ? (
                  <div className="flex flex-col gap-3 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-k-body font-medium">Verdict</span>
                      <span
                        className={
                          activeIncident.gate_verdict === "ALLOW"
                            ? "text-k-success font-mono font-bold"
                            : "text-k-danger font-mono font-bold"
                        }
                      >
                        {activeIncident.gate_verdict}
                      </span>
                    </div>
                    <div>
                      <span className="text-k-muted text-xs uppercase tracking-wider block mb-1">
                        Reason
                      </span>
                      <span className="font-mono text-xs bg-k-canvas-soft p-2 rounded border border-k-hairline-soft block leading-relaxed text-k-body">
                        {activeIncident.gate_reason}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-k-muted">Pending...</div>
                )}
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-5 shadow-sm">
                <h3 className="font-semibold mb-4 text-[11px] uppercase tracking-wider text-k-muted border-b border-k-hairline pb-2">
                  Action Plan
                </h3>
                <ActionPlan incident={activeIncident} />
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-5 shadow-sm">
                <h3 className="font-semibold mb-4 text-[11px] uppercase tracking-wider text-k-muted border-b border-k-hairline pb-2">
                  Verification Deltas
                </h3>
                <DeltaStrip deltas={activeIncident.verification_deltas || {}} />
              </div>

              <UndoStackTimeline 
                undoStack={activeIncident.undo_stack} 
                outcome={activeIncident.outcome} 
              />

              {activeIncident.outcome === "MITIGATED" && (
                <div className="bg-k-caution-bg rounded border border-k-caution p-5 flex flex-col gap-3 shadow-sm">
                  <div className="flex flex-col">
                    <span className="font-semibold text-sm text-k-caution">
                      Active Debt
                    </span>
                    <span className="text-xs text-k-caution mt-1 opacity-90">
                      The system is mitigated but running in a degraded state.
                    </span>
                  </div>
                  <button
                    onClick={() => repayDebt(activeIncident.id)}
                    className="w-full px-4 py-2 bg-k-caution text-k-on-primary rounded hover:bg-opacity-90 text-sm font-medium transition-colors"
                  >
                    Repay Debt
                  </button>
                </div>
              )}
              
              <TopologyGraph services={activeIncident.services} />
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}

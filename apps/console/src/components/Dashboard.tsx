"use client";

import { useState, useEffect } from "react";

interface Incident {
  id: string;
  scenario?: string;
  outcome: string;
  fault_class?: string;
  diagnosis?: {
    fault_class: string;
    confidence: number;
    evidence_ids: string[];
  };
  approved_actions?: { name: string; params: Record<string, unknown> }[];
  plan?: unknown[];
  gate_verdict?: string;
  gate_reason?: string;
  verification_deltas?: Record<string, number>;
  simulation_state?: Record<string, unknown>;
}

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
      if (payload.type === "incident_created" || payload.type === "node_completed") {
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
          }
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
        body: JSON.stringify({ scenario_name: name })
      });
      const data = await res.json();
      fetchIncident(data.incident_id);
    } catch (e) {
      console.error(e);
    }
  };

  // Helper to get stage colors
  const getStageColor = (stage: string) => {
    const map: Record<string, string> = {
      detect: "var(--color-k-stage-detect)",
      diagnose: "var(--color-k-stage-diagnose)",
      plan: "var(--color-k-stage-detect)",
      gate: "var(--color-k-stage-evidence)",
      execute: "var(--color-k-stage-execute)",
      verify: "var(--color-k-stage-verify)",
      outcome: "var(--color-k-stage-done)"
    };
    return map[stage] || "var(--color-k-surface-strong)";
  };

  const getOutcomeColor = (outcome: string) => {
    if (outcome === "RESOLVED") return "var(--color-k-success)";
    if (outcome === "MITIGATED") return "var(--color-k-caution)";
    if (outcome === "ESCALATED") return "var(--color-k-danger)";
    if (outcome === "UNRECOVERABLE") return "var(--color-k-unrecoverable)";
    return "var(--color-k-muted)";
  };

  return (
    <div className="flex flex-col min-h-screen bg-k-canvas text-k-ink">
      <header className="h-16 px-6 flex items-center border-b border-k-hairline bg-k-surface">
        <h1 className="text-xl font-semibold tracking-tight text-k-primary">Kavach</h1>
        <div className="ml-auto flex items-center gap-4">
          <button 
            onClick={() => launchScenario("F01")}
            className="px-4 py-2 bg-k-ink text-white rounded hover:bg-opacity-90 text-sm font-medium transition-colors"
          >
            Launch F01
          </button>
          <span className="text-xs px-2 py-1 bg-k-surface-strong rounded text-k-ink uppercase tracking-wider font-semibold">
            SIMULATION
          </span>
        </div>
      </header>

      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6 max-w-[1400px] mx-auto w-full">
        {/* Stream */}
        <section className="flex flex-col gap-6">
          <h2 className="text-2xl font-medium">Active Incidents</h2>
          <div className="flex flex-col gap-3">
            {Object.keys(incidents).length === 0 ? (
              <div className="text-k-muted text-sm bg-k-canvas-soft p-8 rounded border border-k-hairline text-center">
                No incidents. Launch a scenario to begin.
              </div>
            ) : (
              Object.entries(incidents).reverse().map(([id, inc]: [string, Incident]) => (
                <div 
                  key={id} 
                  onClick={() => fetchIncident(id)}
                  className={`p-4 rounded border cursor-pointer transition-colors bg-k-surface hover:border-k-hairline-strong ${activeIncident?.id === id ? 'border-k-primary shadow-sm' : 'border-k-hairline'}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-mono text-sm">{id}</span>
                    <span 
                      className="text-xs px-2 py-1 rounded font-semibold tracking-wider" 
                      style={{ 
                        color: getOutcomeColor(inc.outcome), 
                        backgroundColor: inc.outcome !== 'IN_PROGRESS' ? 'var(--color-k-surface-strong)' : 'transparent',
                        border: inc.outcome === 'IN_PROGRESS' ? '1px solid var(--color-k-hairline-strong)' : 'none'
                      }}
                    >
                      {inc.outcome}
                    </span>
                  </div>
                  <div className="text-sm text-k-muted">Scenario: {inc.scenario || "Unknown"}</div>
                  {inc.fault_class && <div className="text-sm mt-1">Fault: <span className="font-mono">{inc.fault_class}</span></div>}
                </div>
              ))
            )}
          </div>
        </section>

        {/* Inspector */}
        <aside className="flex flex-col gap-6">
          <h2 className="text-2xl font-medium">Inspector</h2>
          {!activeIncident ? (
            <div className="text-k-muted text-sm bg-k-canvas-soft p-8 rounded border border-k-hairline text-center">
              Select an incident to view details.
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              
              {/* Timeline Stage */}
              <div className="flex gap-2 text-[10px] font-bold uppercase tracking-wider overflow-hidden">
                {['detect', 'diagnose', 'plan', 'execute', 'verify', 'outcome'].map((stage) => {
                  const color = getStageColor(stage);
                  return (
                    <div key={stage} style={{ backgroundColor: color }} className="px-3 py-1.5 rounded-full text-k-ink">
                      {stage}
                    </div>
                  );
                })}
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-4">
                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wider text-k-muted">LLM Diagnosis</h3>
                {activeIncident.diagnosis ? (
                  <div className="text-sm flex flex-col gap-2">
                    <div><span className="text-k-muted">Class:</span> <span className="font-mono">{activeIncident.diagnosis.fault_class}</span></div>
                    <div><span className="text-k-muted">Confidence:</span> {(activeIncident.diagnosis.confidence * 100).toFixed(0)}%</div>
                    <div><span className="text-k-muted">Evidence:</span> {activeIncident.diagnosis.evidence_ids.join(", ") || "None"}</div>
                  </div>
                ) : (
                  <div className="text-sm text-k-muted">Pending...</div>
                )}
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-4">
                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wider text-k-muted">Safety Gate (TNR)</h3>
                {activeIncident.gate_verdict ? (
                  <div className="flex flex-col gap-2 text-sm">
                    <div>
                      <span className="text-k-muted">Verdict: </span> 
                      <span className={activeIncident.gate_verdict === "ALLOW" ? "text-k-success font-mono font-semibold" : "text-k-danger font-mono font-semibold"}>
                        {activeIncident.gate_verdict}
                      </span>
                    </div>
                    <div>
                      <span className="text-k-muted">Reason: </span>
                      <span className="font-mono text-xs bg-k-canvas-soft px-1 rounded border border-k-hairline-soft">
                        {activeIncident.gate_reason}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-k-muted">Pending...</div>
                )}
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-4">
                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wider text-k-muted">Action Plan</h3>
                {activeIncident.approved_actions && activeIncident.approved_actions.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    {activeIncident.approved_actions.map((act, i) => (
                      <div key={i} className="text-sm bg-k-canvas-soft p-2 rounded border border-k-hairline-soft font-mono">
                        {act.name}({JSON.stringify(act.params)})
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-k-muted">{activeIncident.gate_verdict === "DENY" ? "Blocked by safety gate" : (activeIncident.plan ? "No actions approved" : "Pending...")}</div>
                )}
              </div>

              <div className="bg-k-surface rounded border border-k-hairline p-4">
                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wider text-k-muted">Verification Deltas</h3>
                {activeIncident.verification_deltas ? (
                  <div className="flex flex-col gap-2 text-sm">
                    {Object.entries(activeIncident.verification_deltas).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span>{k}</span>
                        <span className={v >= 0 ? "text-k-success font-mono" : "text-k-danger font-mono"}>
                          {v > 0 ? "+" : ""}{Number(v).toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-k-muted">Pending...</div>
                )}
              </div>
              
              <div className="bg-k-surface rounded border border-k-hairline p-4">
                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wider text-k-muted">Simulated State</h3>
                <pre className="text-xs font-mono bg-k-canvas-soft p-2 rounded overflow-auto">
                  {JSON.stringify(activeIncident.simulation_state, null, 2)}
                </pre>
              </div>

            </div>
          )}
        </aside>
      </main>
    </div>
  );
}

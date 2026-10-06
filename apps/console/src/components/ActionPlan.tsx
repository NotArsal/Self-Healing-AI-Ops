import React from "react";
import { Incident } from "./types";

export function ActionPlan({ incident }: { incident: Incident }) {
  if (incident.gate_verdict === "DENY") {
    return <div className="text-sm text-k-muted">Blocked by safety gate</div>;
  }
  
  if (!incident.approved_actions || incident.approved_actions.length === 0) {
    return <div className="text-sm text-k-muted">{incident.plan ? "No actions approved" : "Pending..."}</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {incident.approved_actions.map((act, i) => (
        <div key={i} className="flex flex-col gap-2 bg-k-canvas-soft p-3 rounded border border-k-hairline">
          <div className="font-mono text-sm text-k-ink font-medium">{act.name}</div>
          {Object.keys(act.params).length > 0 && (
            <div className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
              {Object.entries(act.params).map(([pk, pv]) => (
                <React.Fragment key={pk}>
                  <div className="text-k-muted font-mono">{pk}:</div>
                  <div className="text-k-body font-mono truncate" title={String(pv)}>{String(pv)}</div>
                </React.Fragment>
              ))}
            </div>
          )}
          <div className="text-xs font-mono text-k-muted mt-1">undo: inverse execution not resolved</div>
        </div>
      ))}
    </div>
  );
}

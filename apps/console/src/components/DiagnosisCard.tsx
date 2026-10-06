import React from "react";
import { Incident } from "./types";

export function DiagnosisCard({ diagnosis }: { diagnosis?: Incident["diagnosis"] }) {
  if (!diagnosis) {
    return <div className="text-sm text-k-muted">Pending...</div>;
  }

  const confScore = diagnosis.confidence;
  const segments = [1, 2, 3, 4, 5];
  const filledSegments = Math.round(confScore * 5);

  return (
    <div className="text-sm flex flex-col gap-4">
      <div>
        <span className="text-k-muted block text-xs uppercase tracking-wider mb-1">Class</span>
        <span className="font-mono text-k-ink">{diagnosis.fault_class}</span>
      </div>
      
      <div>
        <span className="text-k-muted block text-xs uppercase tracking-wider mb-1">Confidence</span>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {segments.map((s) => (
              <div 
                key={s} 
                className={`h-2 w-6 rounded-sm ${s <= filledSegments ? 'bg-k-ink' : 'bg-k-hairline-strong'}`}
              />
            ))}
          </div>
          <span className="font-mono text-k-ink font-semibold">{(confScore * 100).toFixed(0)}%</span>
        </div>
      </div>

      <div>
        <span className="text-k-muted block text-xs uppercase tracking-wider mb-1">Evidence</span>
        <span className="font-mono text-k-body text-xs leading-relaxed">
          {diagnosis.evidence_ids.join(", ") || "None"}
        </span>
      </div>
    </div>
  );
}

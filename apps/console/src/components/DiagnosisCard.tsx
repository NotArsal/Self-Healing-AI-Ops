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
        <div className="flex flex-wrap gap-2">
          {diagnosis.evidence_ids && diagnosis.evidence_ids.length > 0 ? (
            diagnosis.evidence_ids.map((id, index) => {
              const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL;
              // If it looks like a trace ID (e.g. 32 char hex) and Grafana is configured
              const isTrace = /^[a-f0-9]{32}$/i.test(id);
              
              if (grafanaUrl && isTrace) {
                const query = encodeURIComponent(JSON.stringify({ datasource: 'tempo', queries: [{ query: id }] }));
                const href = `${grafanaUrl}/explore?left=${query}`;
                return (
                  <a key={id} href={href} target="_blank" rel="noreferrer" className="font-mono text-xs text-k-primary hover:underline inline-flex items-center gap-1 bg-k-surface px-2 py-1 rounded border border-k-hairline hover:bg-k-canvas-soft">
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                    {id.substring(0, 8)}
                  </a>
                );
              }
              
              return (
                <span key={id} className="font-mono text-k-body text-xs leading-relaxed bg-k-surface px-2 py-1 rounded border border-k-hairline">
                  {id}
                </span>
              );
            })
          ) : (
            <span className="font-mono text-k-body text-xs leading-relaxed">None</span>
          )}
        </div>
      </div>
    </div>
  );
}

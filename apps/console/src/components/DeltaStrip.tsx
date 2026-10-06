import React from "react";

export function DeltaStrip({ deltas }: { deltas: Record<string, number> }) {
  if (!deltas || Object.keys(deltas).length === 0) {
    return <div className="text-sm text-k-muted">Pending...</div>;
  }

  return (
    <div className="flex flex-col gap-3">
      {Object.entries(deltas).map(([key, value]) => {
        // Just a basic heuristic for delta color
        const isPositive = value >= 0;
        const colorClass = isPositive ? "text-k-success" : "text-k-danger";
        const sign = isPositive ? "+" : "";
        
        return (
          <div key={key} className="flex flex-col gap-1">
            <div className="flex justify-between items-baseline">
              <span className="text-sm font-medium">{key}</span>
              <span className={`font-mono text-sm ${colorClass}`}>
                {sign}{(value * 100).toFixed(1)}%
              </span>
            </div>
            {/* Simple visual bar */}
            <div className="h-1.5 w-full bg-k-hairline-strong rounded overflow-hidden">
              <div 
                className={`h-full ${isPositive ? 'bg-k-success' : 'bg-k-danger'}`} 
                style={{ width: `${Math.min(Math.abs(value * 100), 100)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

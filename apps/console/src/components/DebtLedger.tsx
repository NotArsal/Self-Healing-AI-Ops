"use client";

import { useState, useEffect } from "react";

export interface ActiveDebt {
  incident_id: string;
  scenario_id: string;
  fault_class: string;
  created_at: number;
  trigger_condition: string;
  trigger_value: number;
  max_age_s: number;
  repayment_action: string;
}

export function DebtLedger() {
  const [debts, setDebts] = useState<ActiveDebt[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/v1/debts/")
      .then(res => res.json())
      .then(data => {
        setDebts(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="p-6">
        <p className="text-k-muted">Loading ledger...</p>
      </div>
    );
  }

  if (debts.length === 0) {
    return (
      <div className="p-12 flex flex-col items-center justify-center border-b border-k-hairline">
        <p className="text-k-muted font-medium">No outstanding debts. Kavach is fully remediated.</p>
        <button className="mt-4 px-4 py-2 text-sm border border-k-hairline rounded bg-k-surface text-k-ink">Return to Dashboard</button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h2 className="text-lg font-medium mb-6 uppercase tracking-wider">Outstanding Debt Ledger</h2>
      <div className="flex flex-col gap-4">
        {debts.map(debt => {
          const ageS = Math.floor(Date.now() / 1000 - debt.created_at);
          const isOverdue = ageS > debt.max_age_s;
          
          return (
            <div key={debt.incident_id} className="border border-k-hairline bg-k-surface rounded-md p-4 flex justify-between items-start">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="font-mono text-sm bg-k-canvas px-2 py-0.5 rounded border border-k-hairline">
                    {debt.fault_class}
                  </span>
                  <span className="text-sm font-medium">Incident {debt.incident_id.substring(0, 8)}</span>
                </div>
                
                <p className="text-sm text-k-body mt-2">
                  <span className="font-medium text-k-ink">Owed Action: </span> 
                  <span className="font-mono bg-k-canvas px-1 rounded text-k-muted">{debt.repayment_action}</span>
                </p>
                <p className="text-sm text-k-body mt-1">
                  <span className="font-medium text-k-ink">Trigger: </span> 
                  {debt.trigger_condition} (Threshold: {debt.trigger_value})
                </p>
              </div>
              
              <div className="text-right">
                <p className={`font-mono text-sm ${isOverdue ? "text-k-danger" : "text-k-muted"}`}>
                  Age: {ageS}s / {debt.max_age_s}s
                </p>
                {isOverdue && (
                  <span className="inline-block mt-1 text-xs font-medium bg-k-danger/10 text-k-danger px-2 py-0.5 rounded">OVERDUE</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

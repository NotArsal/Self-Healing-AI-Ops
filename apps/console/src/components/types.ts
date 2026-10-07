export interface UndoRecord {
  original_action: { name: string; params: Record<string, unknown> };
  inverse_action: { name: string; params: Record<string, unknown> };
  pre_state_witness: Record<string, unknown>;
  applied: boolean;
}

export interface Incident {
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
  debt?: Record<string, unknown>;
  undo_stack?: UndoRecord[];
  services?: Record<string, { role: string; depends_on?: string[] }>;
}

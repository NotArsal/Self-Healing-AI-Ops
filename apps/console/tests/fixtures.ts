/**
 * Fixtures shaped from real P3 output.
 *
 * They are typed against the GENERATED client types, not hand-written
 * interfaces. That is the point: if a backend field changes and
 * `make gen-client` regenerates, these fixtures stop compiling and `pnpm types`
 * fails — which is the "a backend schema change breaks the frontend" guarantee,
 * enforced by the test data itself rather than by a reminder.
 */

import type {
  FleetMetrics,
  Incident,
  IncidentSummary,
  LoopEvent,
  ModeState,
  Preflight,
  System,
} from "@/lib/api";

export const system: System = {
  kavach_version: "0.1.0",
  mode: "SIMULATION",
  mode_is_enforced: false,
  project: "simple-rag",
  target_path: "D:/Target_RAG-App",
  compose_project: "target_rag-app",
  rerank_threshold: 0.35,
  config_hash: "9f1c2ab4",
  corpus: { chunks: 30, files: 2 },
  loop_running: false,
  running_incident_id: "",
  dependencies: [
    { name: "Kavach control plane", ok: true, detail: "version 0.1.0", endpoint: "self" },
    { name: "Target application", ok: true, detail: "ok", endpoint: "http://localhost:8000/healthz" },
    { name: "Target database", ok: true, detail: "pool 0/10", endpoint: "postgres (via target)" },
    { name: "Ollama, target path", ok: true, detail: "reachable", endpoint: "via Toxiproxy" },
    { name: "Ollama, Kavach path", ok: true, detail: "model llama3.2", endpoint: "http://localhost:11434 (direct, never proxied)" },
    { name: "Prometheus", ok: true, detail: "responding to instant queries", endpoint: "http://localhost:9091" },
    { name: "Baseline capture", ok: true, detail: "rerank_threshold 0.35", endpoint: "harness/baselines/" },
  ],
};

export const resolvedIncident: Incident = {
  incident_id: "INC-104512",
  project: "simple-rag",
  status: "RESOLVED",
  detected_at: "2026-10-04T10:45:12+00:00",
  resolved_at: "2026-10-04T10:46:08+00:00",
  fault_class: "F06",
  fault_name: "retrieval_collapse",
  service: "backend",
  diagnosed_by: "llm_rca",
  outcome: "resolved: rerank_threshold 0.999 -> 0.35 (restored from baseline)",
  escalation_reason: "",
  awaiting_approval: false,
  decision: {
    verdict: "ALLOW_AUTO",
    action: "rollback_config",
    risk_tier: "MEDIUM",
    mode: "AUTONOMOUS",
    reasons: [],
    checks: [
      { name: "project_ownership", passed: true, detail: "backend in target_rag-app" },
      { name: "deny_list", passed: true, detail: "no denied mutation or parameter" },
      { name: "allow_list", passed: true, detail: "rollback_config" },
      { name: "inverse_recorded", passed: true, detail: "pre-state witness captured" },
    ],
    at: "2026-10-16T10:45:44+00:00",
  },
  unwind: null,
  planned_action: "rollback_config",
  corpus_before: { chunks: 30, files: 2 },
  corpus_after: { chunks: 30, files: 2 },
  corpus_unchanged: true,
  detection: {
    verdict: "RETRIEVAL_COLLAPSE",
    fault_class: "F06",
    fault_name: "retrieval_collapse",
    service: "backend",
    reasons: ["similarity healthy at 0.658 while zero chunks were kept"],
    evidence: [],
    pre_verification: null,
  },
  rca: {
    at: "2026-10-04T10:45:40+00:00",
    model: "llama3.2",
    latency_s: 2.2,
    prompt_tokens: 1840,
    completion_tokens: 210,
    approved: true,
    approved_action: "rollback_config",
    error: "",
    confidence_is_calibrated: false,
    evidence_collected_at: "2026-10-04T10:45:38+00:00",
    evidence_problems: [],
    diagnosis: {
      fault_class: "F06",
      fault_name: "retrieval_collapse",
      service: "backend",
      confidence: 0.9,
      evidence_ids: ["EV-M02", "EV-L06"],
      reasoning:
        "EV-M01 shows similarity 0.658 which is healthy, while EV-M02 shows zero chunks kept.",
      candidate_repair: "rollback_config",
      rejected_alternatives: [
        { fault_class: "F01", reason: "EV-M06 shows llm_error_ratio 0.0" },
      ],
    },
    validation: {
      outcome: "ACCEPTED",
      approved_action: "rollback_config",
      rejection_reasons: [],
      checks: [
        { name: "schema_valid", passed: true, detail: "parsed and schema-validated" },
        { name: "actionable_claim", passed: true, detail: "fault_class F06" },
        { name: "fault_class_supported", passed: true, detail: "F06" },
        { name: "confidence_threshold", passed: true, detail: "0.90 >= 0.75" },
        { name: "citations_resolve", passed: true, detail: "2 cited, all resolve" },
        { name: "service_declared", passed: true, detail: "backend" },
        { name: "repair_permitted", passed: true, detail: "rollback_config" },
        { name: "deterministic_agreement", passed: true, detail: "both agree: F06 on backend" },
        { name: "baseline_available", passed: true, detail: "rerank_threshold 0.35" },
        { name: "corpus_intact", passed: true, detail: "30 chunks" },
      ],
    },
    evidence: [
      { eid: "EV-M01", kind: "metric", name: "retrieval_top_similarity", value: "0.658", expected: "0.4 to 0.9", note: "" },
      { eid: "EV-M02", kind: "metric", name: "retrieval_chunks_kept", value: "0.0", expected: "at least 1", note: "" },
      { eid: "EV-C01", kind: "config", name: "rerank_threshold", value: "0.999", expected: "", note: "" },
      { eid: "EV-L06", kind: "log", name: "backend_log", value: "reranked 0 of 5 chunks above threshold", expected: "", note: "" },
    ],
  },
  action: {
    incident_id: "INC-104512",
    action: "rollback_config",
    risk_tier: "MEDIUM",
    idempotency_key: "INC-104512:rollback_config:0.35",
    requested_settings: { rerank_threshold: 0.35 },
    inverse_settings: { rerank_threshold: 0.999 },
    config_hash_before: "11aabb22",
    config_hash_after: "9f1c2ab4",
    executed: true,
    reverted: false,
    prepared_at: "2026-10-04T10:45:44+00:00",
    executed_at: "2026-10-04T10:45:45+00:00",
    error: "",
  },
  verification: {
    passed: true,
    health_ok: true,
    health_detail: "database and ollama ok",
    quality_ok: true,
    within_budget: true,
    pass_rate: 1,
    total_s: 18.4,
    budget_s: 120,
    repair_applied: { ok: true, detail: "rerank_threshold is 0.35" },
    scope_respected: { ok: true, detail: "no other setting changed" },
    cases: [
      { case_id: "fv-01", passed: true, keyword_present: true, non_refusal: true, sources_block: true, latency_s: 6.1, error: "" },
      { case_id: "fv-02", passed: true, keyword_present: true, non_refusal: true, sources_block: true, latency_s: 5.9, error: "" },
      { case_id: "fv-03", passed: true, keyword_present: true, non_refusal: true, sources_block: true, latency_s: 6.4, error: "" },
    ],
  },
};

export const summaries: IncidentSummary[] = [
  {
    incident_id: resolvedIncident.incident_id,
    project: "simple-rag",
    status: "RESOLVED",
    detected_at: resolvedIncident.detected_at,
    resolved_at: resolvedIncident.resolved_at,
    fault_class: "F06",
    fault_name: "retrieval_collapse",
    service: "backend",
    diagnosed_by: "llm_rca",
    outcome: resolvedIncident.outcome,
  },
];

export const events: LoopEvent[] = [
  { seq: 1, at: "2026-10-04T10:45:12.100+00:00", incident_id: "INC-104512", stage: "run", status: "started", message: "operator started a loop run" },
  { seq: 2, at: "2026-10-04T10:45:30.000+00:00", incident_id: "INC-104512", stage: "detect", status: "ok", message: "detected F06 retrieval_collapse on backend" },
  { seq: 3, at: "2026-10-04T10:45:38.000+00:00", incident_id: "INC-104512", stage: "evidence", status: "ok", message: "evidence collected: 33 citable items" },
  { seq: 4, at: "2026-10-04T10:45:40.000+00:00", incident_id: "INC-104512", stage: "diagnose", status: "ok", message: "diagnosis returned: F06 retrieval_collapse on backend" },
];

export const preflight: Preflight = {
  project: "simple-rag",
  passed: false,
  blocking_count: 1,
  ran_at: "2026-10-04T10:40:00+00:00",
  error: "",
  checks: [
    { name: "manifest parses", passed: true, skipped: false, status: "PASS", detail: "kavach/v1", remediation: "" },
    { name: "git branch is kavach/ops", passed: true, skipped: false, status: "PASS", detail: "on kavach/ops", remediation: "" },
    { name: "ollama reachable", passed: false, skipped: true, status: "SKIP", detail: "could not probe", remediation: "Start Ollama on port 11434" },
  ],
};

export const awaitingIncident: Incident = {
  ...resolvedIncident,
  incident_id: "INC-110233",
  status: "AWAITING_APPROVAL",
  resolved_at: "",
  awaiting_approval: true,
  outcome: "REQUIRE_APPROVAL: planned rollback_config, not executed",
  verification: null,
  decision: {
    verdict: "REQUIRE_APPROVAL",
    action: "rollback_config",
    risk_tier: "MEDIUM",
    mode: "APPROVAL",
    reasons: ["mode_policy: REQUIRE_APPROVAL under APPROVAL for a MEDIUM-risk action"],
    checks: [
      { name: "project_ownership", passed: true, detail: "backend in target_rag-app" },
      { name: "deny_list", passed: true, detail: "no denied mutation or parameter" },
      { name: "allow_list", passed: true, detail: "rollback_config" },
      { name: "inverse_recorded", passed: true, detail: "pre-state witness captured" },
      { name: "mode_policy", passed: true, detail: "APPROVAL + MEDIUM -> REQUIRE_APPROVAL" },
    ],
    at: "2026-10-16T11:02:33+00:00",
  },
};

export const modeState: ModeState = {
  mode: "APPROVAL",
  enforced: true,
  manifest_mode: "APPROVAL",
  overridden: false,
  allowed_actions: ["rollback_config"],
  denied_mutations: ["data_delete", "database_drop", "embed_model_change",
                     "migration", "scale_to_zero"],
  confidence_threshold: 0.75,
};

export const metrics: FleetMetrics = {
  available: true,
  incidents: 12,
  resolved: 9,
  escalated: 2,
  awaiting: 1,
  auto_healed: 9,
  mttr_seconds: 58.4,
  repair_success_rate: 0.818,
  unavailable_reason: "",
};

/** No database: every rate must be null, never zero. */
export const emptyMetrics: FleetMetrics = {
  available: false,
  incidents: 0,
  resolved: 0,
  escalated: 0,
  awaiting: 0,
  auto_healed: 0,
  mttr_seconds: null,
  repair_success_rate: null,
  unavailable_reason: "could not connect",
};

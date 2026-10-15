# Kavach: Autonomous Self-Healing Control Plane

Kavach is an autonomous self-healing control plane designed to detect, diagnose, and mitigate infrastructure and application faults in real-time. It leverages advanced LLM-driven Root Cause Analysis (RCA) via Ollama, zero-shot Task Negative Representation (TNR) safety gating via Laya, and an interactive Next.js console for operators to observe the autonomous pipelines.

## Key Capabilities
- **LLM-Driven RCA**: Uses Qwen/Llama running locally via Ollama to diagnose complex cascading failures (F01-F12 taxonomy).
- **Topology-Aware**: Incorporates a lightweight dependency graph to trace faults to their true root cause (e.g., distinguishing between a degraded API and a dead database).
- **TNR Safety Gate**: Evaluates the destructive probability of auto-generated remediation commands (e.g., `rm -rf`) using Laya. Includes a custom fine-tuning pipeline to calibrate Laya's thresholds to organizational policies.
- **Agentic State Graph**: Implemented with LangGraph, orchestrating the full lifecycle: Detect -> Diagnose -> Plan -> Gate -> Execute -> Verify -> Unwind.
- **Frontend Console**: A Next.js dashboard providing real-time visibility into incidents, remediation plans, and gate verdicts.

## Architecture
- **Control Plane**: FastAPI (Backend API), LangGraph (Workflow), Laya (Safety Gate), Ollama (RCA).
- **Console**: Next.js 15, React 19, Tailwind CSS.

## Getting Started
1. Start Ollama: `ollama serve` (needs `qwen2.5:7b-instruct` pulled)
2. Start the Control Plane: `cd apps/control-plane && uv run uvicorn kavach.main:app --port 8000`
3. Start the Console: `cd apps/console && pnpm dev`
4. Simulate Alerts: `cd apps/control-plane && uv run python simulate_alert.py`

## The live F01 loop

`F01` (provider outage) runs against a real application, `targets/proof2`. No
part of this path is simulated: detection probes the app over HTTP, the repair
writes to its admin endpoint, verification runs its golden set, and the undo
reads back the witnessed prior value.

```bash
make target-up                              # the application under management
make onboard APP=targets/proof2             # preflight + capture healthy baseline
make dev-api-live                           # control plane, detection on a 15s tick
make inject FAULT=F01                       # break the primary provider
```

Within one tick the control plane opens an incident on its own, diagnoses `F01`,
switches the app to its backup model, and verifies by re-measuring. The expected
outcome is **`MITIGATED`, not `RESOLVED`**: availability is restored, the golden
set scores a real 10% quality drop on the backup model, and debt is owed because
the primary is still down. Outstanding debt is visible at `/api/v1/debts/`.

Then `make revert FAULT=F01`. Once the application has been continuously healthy
for the dwell its manifest declares (30s for this target), the debt checker
repays: it switches back to the primary *through the same safety gate*, verifies
again, clears the debt and moves the incident to `RESOLVED`.

Requires `make up` and `make migrate` first — debt is persisted in Postgres.

Run `make test-integration` to execute that loop as a test: 12 assertions
against the real application in about 35 seconds. It starts its own copy of the
target, so `make target-up` must not be running.

## Project status

Honest summary, because the distinction matters for how results are read:

| Area | State |
|---|---|
| `F01` against a live app | **Real** — detection, repair, verification, undo, and the full debt lifecycle through to `RESOLVED` |
| `F02`–`F09` | Simulated: the loop runs against an in-memory state dict, and `verification/probes.py` derives metrics from thresholds rather than measuring |
| Contract (`CONTRACT.md` v1.1) | Proof #2 onboarded; six defects found and closed (`docs/decisions/proof2_defects.md`) |
| Measurements | **Real** — see `docs/MEASUREMENTS.md`, generated from `eval_results/*.json`. Undo ablation 100% vs 0% state restoration across three arms, with an ineffective rollback detected 5/5 as `UNRECOVERABLE`; RCA accuracy 100% over 45 injections with no answer key in the prompt. Human baseline **not run** |
| Failing closed | **No** — on a scenario built to be undiagnosable, the model answers a fault class at confidence 0.85 on 5/5 reps and the repair executes. `docs/MEASUREMENTS.md` §3.1. The accuracy figure above does not transfer to ambiguous evidence |
| Audit log | **Real** — append-only `audit_log` with a hash chain, enforced by a database trigger that refuses UPDATE, DELETE and TRUNCATE. Five events per incident; read at `/api/v1/audit/`, integrity at `/api/v1/audit/integrity` |
| Knowledge base (F-MEM) | **Real** — incidents are embedded and stored, and recalled by similarity into the diagnosis evidence. Needs `make up` plus Ollama for `nomic-embed-text` |
| Incident persistence | In-memory only; no `PostgresSaver` checkpointer, so approvals and the debt dwell clock do not survive a restart |
| Risk tiers and the sandbox | **Real** — F03 and F07 load MEDIUM and prove the repair in an isolated dry run before it is executed; a failed dry run stops the repair and leaves the application untouched |
| Undo | **Real** — the live adapter reads the state back after restoring it and reports `UNRECOVERABLE` on a mismatch; `tests/test_unwind.py` asserts the restoration per fault |
| Preflight P01–P14 | **Real** — 13 of 14 checks measure the application: TCP and HTTP probes, a full golden-set run, objective probes, reversible-state reads, catalogue adapter and inverse resolution, git worktree state, baseline on disk. A check the platform cannot establish reports `UNVERIFIED`, which earns no conformance level |
| Telemetry ingestion | **Not built.** `kavach/telemetry/` and `kavach/evidence/` are empty directories; there is no ingestion route and no GenAI normalisation (`ARCHITECTURE.md` §2.3). This is what caps `targets/proof2` at `UNARMED` — preflight P12 has nothing to check spans against |
| `make check` | Red: 79 mypy errors, 48 ruff errors, all outside the modules listed above |

Phase-by-phase claims in `PROJECT_COMPLETION_REPORT.md` predate this table and
overstate what runs; prefer this section.

# Proof 2 Onboarding Defects

During the execution of Proof #2 (Phase 9b), the following contract defects were discovered.

**Status (2026-10-14):** defects #1, #2, #3 and #4 are closed by `CONTRACT.md`
v1.1 and ADR-002. Defect #5 was found afterwards, while making the F01 loop
measure a live application, and is also closed by v1.1 §5.1.

| # | Defect | Closed by |
|---|---|---|
| 1 | No dynamic target resolution | `scenarios/from_manifest.py` — incidents are projected from any application's `kavach.yaml` |
| 2 | `runtime_config` protocol unspecified | `CONTRACT.md` §6.1 |
| 3 | Actions unmapped to reversible state | catalogue `effect` block; `field`/`values` in §6.1 |
| 4 | No HTTP action executor | `remediation/runtime_config.py` |
| 5 | Unmeasurable objectives pass silently | `CONTRACT.md` §5.1 |
| 6 | Debt key's binding to a fault class unspecified | `CONTRACT.md` §10.1 — the key is the fault class ID |

The point of the log is that each one was a *missing obligation*, not a missing
feature: every fix is a sentence the specification should have contained.

## 1. No Dynamic Target Resolution
**Defect:** Kavach relies on hardcoded scenario routing in `/api/v1/alerts/webhook` (mapping "application" to F10 and "database" to F11) rather than dynamically parsing the target application's `kavach.yaml` based on the alert metadata.
**Obligation:** The platform must parse incoming alerts to identify the target, read its `kavach.yaml` dynamically, and construct the `IncidentState` (`Scenario`) from it.

## 2. Incomplete Specification for `runtime_config`
**Defect:** `CONTRACT.md` allows `kind: runtime_config` with `read` and `write` endpoints but does not define the HTTP protocol details (Method, Headers, Body format).
**Obligation:** The contract must specify standard OpenAPI definitions or enforce a strict HTTP contract (e.g. `POST` with a JSON body) so the executor knows how to construct the mutation request.

## 3. Unmapped Allowed Actions
**Defect:** The `permissions.allowed_actions` array declares actions like `switch_model`, but there is no mechanism to bind an action to a specific `reversible_state` operation. The executor has no way of knowing that `switch_model` means hitting the `write` endpoint of the `model_selection` state.
**Obligation:** Allowed actions must explicitly map to the corresponding `reversible_state` keys, providing the exact payload or parameters to be used.

## 4. Missing HTTP Action Executor
**Defect:** The Kavach platform execution layer (`execute_node`) only supports `shell_command` via `subprocess.run` (or the mock simulation executor). It lacks an HTTP adapter capable of executing `runtime_config` state changes over HTTP.
**Obligation:** The executor must natively support an HTTP action adapter capable of interacting with `runtime_config` endpoints, verifying success via HTTP status codes, and capturing inverses.

## 5. Unmeasurable Objectives Pass Silently
**Defect:** An application can declare a conformant objective whose metric the platform has no way to read (anything requiring a Prometheus query, since the healing loop must not depend on the metrics stack). Verification skipped the objective and still reported a pass, so an unverified objective was indistinguishable from a satisfied one. Relatedly, nothing in the contract required a healthy baseline, so deltas could only be measured against the breach — which scores a degraded repair as an improvement.
**Obligation:** The contract must state which metrics a conforming platform can measure, require onboarding to report the ones it cannot, forbid treating an unmeasurable objective as satisfied, and require a healthy baseline captured at onboarding for deltas to be measured against.

## 6. Debt Key Binding Unspecified
**Defect:** The `debt` map's example key was a descriptive label (`f01_provider_outage`) and the contract never said how it bound to a fault class. The platform looked debt up by fault class, so the lookup never matched and **no `MITIGATED` outcome ever recorded a debt** — the whole of §10.1 was unreachable. An onboarder reading v1 had no way to know what the key had to be.
**Obligation:** The key is the fault class ID the entry repays. The readable name remains available from the fault catalogue.

### Found alongside, as platform bugs rather than contract defects

These are recorded here because they were discovered by the same exercise and each one independently prevented debt from working:

- `alembic upgrade head` failed on a clean database: a TimescaleDB continuous aggregate was created `WITH DATA`, which cannot run inside a transaction block. Migration `0001` aborted, so `remediation_debt` never existed. Fixed with `WITH NO DATA`.
- `kavach/api/db.py` defaulted to password `postgres` while `infra/docker-compose.yml` creates the container with `password`. Every debt and knowledge write failed authentication and was swallowed by a bare `except`.
- The debt trigger's dwell (`healthy_for_s: 600`) was declared but never persisted; the checker passed `value=0`, so a debt would have repaid the instant the provider first looked healthy. Added `trigger_value` (migration `0004`) and a dwell state machine.
- `scenario.active_debt_def` was assigned to a Pydantic model that did not declare the field, which raises. It was unreachable only because the key lookup above it already failed.
- `repay_debt` called `.clear()` on `active_debt` without a None guard, raising *after* the live write had landed — repaid application, outstanding debt.

### Found by the measurement work (2026-10-15)

- **The catalogue loader overwrites instead of merging.** `load_catalogue` does
  `catalogue.faults[id] = fault` per file, so a per-fault YAML replaces
  `core.yaml`'s entry wholesale. `core.yaml` declares F03 as MEDIUM risk with a
  `detect` signal, and F07 likewise; `f03.yaml` and `f07.yaml` redefine those
  faults without either field, so both are silently dropped. Consequences:
  every fault now loads as `risk=LOW`, and only F01 retains a `detect` signal.
- **The risk tier table is therefore flat.** Because nothing loads as MEDIUM,
  `plan_node` never sets `sandbox_required`, so the F-SBX sandbox branch is
  unreachable for every real fault — its test passes only because it mocks
  `load_catalogue` with a MEDIUM fault. Under `AUTONOMOUS`, every repair
  auto-executes with neither a sandbox nor an approval.
- **No rules baseline exists.** PRD §11.2 asks for Phase 3's symptom mapping
  against the LLM on identical injections. That mapping was replaced by the
  catalogue, and with `detect` surviving for F01 only there is nothing to run it
  from. The comparison is unavailable rather than unfavourable.
- **The unwind is never verified.** The undo ablation showed a no-undo run and a
  working run reporting the same outcome (`ESCALATED`); only inspecting the
  application revealed that one had been left mutated. `UNRECOVERABLE` is raised
  solely by the `_force_undo_failure` test flag, so Kavach does not check that
  its own rollback achieved anything. ROADMAP P3 requires a forced-undo-failure
  path to report `UNRECOVERABLE` with a loud alert; it currently cannot.
- **`PROJECT_COMPLETION_REPORT.md` is contradicted by measurement.** It claims
  shadow Laya "correctly aligns with the rule engine 100% of the time". Measured
  agreement is 2/9 (22%).


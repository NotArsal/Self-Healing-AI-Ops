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


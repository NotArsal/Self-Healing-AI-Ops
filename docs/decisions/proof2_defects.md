# Proof 2 Onboarding Defects

During the execution of Proof #2 (Phase 9b), the following contract defects were discovered:

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


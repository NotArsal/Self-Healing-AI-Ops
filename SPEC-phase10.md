# Spec: Phase 10 - End-to-End Autonomous Remediation Integration

## Objective
Wire the Laya TNR gate and Executor into Kavach's LangGraph incident lifecycle (`kavach.graph.workflow`), replacing the static simulated `gate_node` and `execute_node` with the actual Laya-powered TNR safety engine and the local shell executor.

## Current State vs Target State
**Current State (Phase 1-8)**: 
- `plan_node` hardcodes responses from a YAML catalogue.
- `gate_node` statically checks an allow-list in the scenario definition.
- `execute_node` mutates a static dictionary `simulation_state` in memory.

**Target State (Phase 10)**:
- `plan_node` outputs string CLI commands (e.g. `kubectl restart pod api` or `systemctl restart db`).
- `gate_node` queries Laya via `tnr_gate.evaluate_safety(command, context)`. If safe, ALLOW. If high-risk, DENY (escalate).
- `execute_node` calls `executor.execute_command()` which actually executes the string command on the host.
- `verify_node` uses Laya via `log_filter.py` or `executor.verify_execution()` to read the terminal output and assert success.

## Scope Limits
- Because we are on a Windows host without a real Kubernetes cluster, the `execute_node` will execute dummy local commands (e.g., `echo "Fixed"`, `ping`) to prove the loop works without breaking the host. 
- The goal is to prove the *architecture* (LLM -> Laya Gate -> Subprocess), not to fix a real Windows issue.

## Technical Plan
1. **Update Node Definitions**: Refactor `kavach.graph.nodes` to import the Phase 9 modules (`evaluate_safety`, `execute_command`, `verify_execution`).
2. **Dynamic Generation**: Allow `plan_node` to pass actual string commands through the graph state.
3. **Run an E2E Test**: Send a request to `/incidents/run` and watch the incident transition from `detect` -> `diagnose` -> `gate` (Laya) -> `execute` (Subprocess) -> `verify` (Laya) -> `MITIGATED`.

## Success Criteria
- The LangGraph workflow successfully uses `laya` to approve a command.
- The workflow executes a safe shell command on the host.
- The workflow escalates if the command is destructive.

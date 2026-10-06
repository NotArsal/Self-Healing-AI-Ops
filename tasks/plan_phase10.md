# Implementation Plan: Phase 10 - End-to-End Remediation Integration

## Overview
Wire the Laya TNR gate and Executor into Kavach's LangGraph incident lifecycle (`kavach.graph.nodes`), replacing the static simulated `gate_node` and `execute_node`.

## Architecture Decisions
- The `plan_node` currently returns a list of `Action` objects (name, params). We will update it to also return a raw shell command for testing (e.g. `Action(name="shell_command", params={"cmd": "echo 'restarted api'"})`).
- The `gate_node` will iterate through planned actions. If it's a `shell_command`, it queries `evaluate_safety` from `tnr_gate.py`.
- The `execute_node` will call `execute_command` for shell commands and capture the output.
- The `verify_node` will call `verify_execution` on the output.

## Task List

### Phase 1: Wire the LangGraph Nodes
- [ ] Task 1: Update `kavach.tnr.models` to support raw string commands (or assume params['cmd']).
- [ ] Task 2: Refactor `gate_node` in `kavach/graph/nodes.py` to use `tnr_gate.evaluate_safety`.
- [ ] Task 3: Refactor `execute_node` to use `remediation.executor.execute_command`.
- [ ] Task 4: Refactor `verify_node` to use `remediation.executor.verify_execution`.

### Checkpoint: Foundation
- [ ] Unit tests for `nodes.py` pass.

### Phase 2: Live Integration
- [ ] Task 5: Add a new dummy scenario (e.g. `F10`) that triggers a safe shell command and another (`F11`) that triggers a destructive shell command.
- [ ] Task 6: Run an end-to-end incident via the `/incidents/run` API.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Executor hangs the backend process | High | Executor has a 30s timeout configured. |

# ADR-001: Declarative Catalogue & TNR Safety Gates

## Status
Accepted

## Date
2026-10-04

## Context
Kavach acts as an autonomous AI platform that executes mitigation strategies in production-like systems. During early simulation (Phase 2), mitigation actions (like `switch_model`) and their respective inverse definitions were hardcoded inside Python scripts (`executor.py` and `plan_node`).

As the platform scales to handle many scenarios (F01 through F09, and eventually arbitrary faults), relying on Python `if/else` branches to map new actions or write undo-records introduces severe operational overhead and safety risks. Furthermore, placing total trust in the LLM planner introduces the risk of "hallucinated" actions and catastrophic state execution (e.g. `drop_database`).

We need:
1. A way to strictly enforce execution boundaries (Trust & Resilience).
2. A generic platform that doesn't require Python patches to add a new fault template.

## Decision
1. **Safety Gate (TNR)**: Introduced a dynamic `gate_node` within the LangGraph state machine. It strictly enforces:
   - **Circuit Breaking**: If the system fails verification and loops more than 3 times, the circuit trips (`CIRCUIT_BREAKER_TRIPPED`) and escalates to human control.
   - **Allow-list Enforcer**: Actions proposed by the LLM that do not exist in the defined scenario's `permissions.allowed_actions` are proactively blocked (`UNAPPROVED_ACTION`).
   - **Blast Radius Caps**: If a plan affects too many simultaneous components, it is denied (`BLAST_RADIUS_EXCEEDED`).
2. **Declarative Catalogue Engine**: Developed a Pydantic-powered schema (`ActionDef`, `InverseDef`, `FaultDef`) that loads YAML-based catalogues into an in-memory dictionary on startup. The `execute_action` logic was refactored to consume generic config-driven templates (e.g., `mutations: {active_model: $fallback}`) to enact state changes, trace witnesses, and dynamically construct `UndoRecords`.

## Alternatives Considered

### Stateful Chat History for Retry Loops
- **Pros:** The LLM could self-correct if the gate denies an action by reasoning through the error response.
- **Cons:** Dramatically increases token consumption, reduces determinism, and complicates the MVP architecture.
- **Rejected:** In the current phase, deterministic deterministic fallback looping is safer and more predictable. 

### Hardcoded `executor.py` Expansion
- **Pros:** Faster time-to-market; extremely explicit type checking.
- **Cons:** Adding a new fault requires rebuilding and deploying the control-plane container.
- **Rejected:** Conflicts with the fundamental "platform" requirement of Kavach. Declarative logic separates system code from business logic.

## Consequences
- The system is now significantly more resilient against LLM hallucinations.
- Developers can add new mitigation strategies (e.g., `F99`) strictly by authoring YAML (`catalogue_data/*.yaml`), accelerating Phase 7 scenario expansions.
- A new validation rule ensures the platform crashes *on startup* if a catalogue developer forgets to map an `inverse` action to an existing action, fulfilling the TNR promise natively.

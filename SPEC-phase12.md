# Spec: Phase 12 - Knowledge Graph Integration

## Objective
Provide Qwen's Root Cause Analysis (RCA) engine with topological context by integrating a Knowledge Graph that models the relationships, dependencies, and health statuses of all services in the system.

## Current State
- The `diagnose_node` relies solely on raw telemetry strings to determine the fault class.
- The system lacks an awareness of the physical layout of the infrastructure (e.g., if Service A calls Service B, and B is down, A will also show errors).

## Target State
1. **Graph Model**: Implement a lightweight knowledge graph (e.g., using NetworkX or a custom graph structure) that loads topological data (services and their dependencies).
2. **Context Enrichment**: The RCA engine (Qwen) should receive a subgraph or textual representation of the dependency chain relevant to the alert.
3. **Advanced RCA**: Qwen uses the topological context alongside telemetry evidence to distinguish between a *symptom* (e.g., frontend latency) and the *root cause* (e.g., database connection timeout).

## Architecture Details
- Create `kavach/topology/graph.py` to hold the dependency graph.
- Load the existing `services` and `depends_on` data from scenarios into the graph.
- Update `kavach.llm.rca.analyze_root_cause` to include the upstream/downstream dependencies in the prompt.

## Success Criteria
- The backend successfully parses `scenario.services` into a topological graph.
- The LLM prompt includes dependency information (e.g., "Service A depends on Service B").
- The system correctly diagnoses cascading failures based on topology, not just isolated errors.

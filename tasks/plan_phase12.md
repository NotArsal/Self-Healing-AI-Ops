# Implementation Plan: Phase 12 - Knowledge Graph Integration

## Overview
Implement a topological knowledge graph to enrich Qwen's Root Cause Analysis with service dependency context.

## Task List

### Phase 1: Topology Graph
- [ ] Task 1: Create `apps/control-plane/kavach/topology/graph.py`.
- [ ] Task 2: Implement a lightweight dependency graph builder that parses `scenario.services`.

### Phase 2: Context Enrichment
- [ ] Task 3: Update `analyze_root_cause` in `kavach/llm/rca.py` to extract upstream/downstream context from the topology graph.
- [ ] Task 4: Inject the topological context into the Qwen RCA prompt.

### Phase 3: Validation
- [ ] Task 5: Create a cascading failure scenario `F12.yaml` where Service A fails because Service B is unreachable.
- [ ] Task 6: Validate that Qwen correctly identifies the root cause (Service B) rather than the symptom (Service A) using the new topological context.

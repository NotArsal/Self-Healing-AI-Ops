## Task 1: Create Alembic migration and SQLAlchemy model for `remediation_debt` table.
**Description:** Define the `remediation_debt` table schema (incident_id, action_name, action_params, status, max_age_s, etc.) in SQLAlchemy and generate the Alembic migration.
**Acceptance criteria:**
- [ ] SQLAlchemy model `RemediationDebt` is defined.
- [ ] Alembic migration script is created and applies successfully.
**Verification:**
- [ ] Manual check: `uv run alembic upgrade head` runs without errors.
**Dependencies:** None
**Files likely touched:** `kavach/api/models.py`, `alembic/versions/xxx.py`

## Task 2: Setup FastAPI lifespan background task loop
**Description:** Implement an `asyncio` background task that runs for the duration of the FastAPI app lifecycle. It should periodically query the DB for `PENDING` debt.
**Acceptance criteria:**
- [ ] Lifespan context manager is added/updated in `kavach/api/main.py`.
- [ ] Background loop executes safely without blocking the event loop.
**Verification:**
- [ ] Manual check: Start API and see background loop heartbeat in logs.
**Dependencies:** Task 1
**Files likely touched:** `kavach/api/main.py`, `kavach/api/background.py`

## Checkpoint: Foundation
- [ ] Database migration runs successfully.
- [ ] API starts cleanly and logs background loop heartbeat.

## Task 3: Update Incident Graph to Insert Debt
**Description:** When the `verify_node` returns a `MITIGATED` outcome (e.g. for F01), push a `PENDING` debt record into the database containing the repayment action (the inverse).
**Acceptance criteria:**
- [ ] `MITIGATED` outcomes trigger debt insertion.
- [ ] The debt record stores the correct inverse action and params.
**Verification:**
- [ ] Tests pass: Unit tests for `verify_node` handling MITIGATED state.
**Dependencies:** Task 1
**Files likely touched:** `kavach/graph/nodes.py`

## Task 4: Add Pydantic models for Debt API
**Description:** Create schemas so the UI can fetch outstanding debt.
**Acceptance criteria:**
- [ ] Pydantic `RemediationDebtResponse` schema added.
- [ ] Route `GET /incidents/{id}/debt` or a general debt list is available.
**Verification:**
- [ ] Manual check: Hit the API endpoint and receive valid JSON.
**Dependencies:** Task 1
**Files likely touched:** `kavach/api/schemas.py`, `kavach/api/routes/incidents.py`

## Checkpoint: Debt Creation
- [ ] Injecting F01 and successfully mitigating it creates a row in the `remediation_debt` table.

## Task 5: Implement Prometheus trigger evaluator
**Description:** Inside the background loop, for F01 debt, check if `gen_ai_error_rate` has been < 5% for 600s.
**Acceptance criteria:**
- [ ] Background loop queries Prometheus correctly.
- [ ] Debt triggers when conditions are met.
**Verification:**
- [ ] Tests pass: Mocked Prometheus response triggers debt evaluation.
**Dependencies:** Task 2, Task 3
**Files likely touched:** `kavach/api/background.py`

## Task 6: Hook repayment execution to safety gate
**Description:** When a trigger fires, execute the inverse action using the safety gate `permit()` and executor logic, then update incident status to `RESOLVED`.
**Acceptance criteria:**
- [ ] Repayment action passes through `safety.engine.permit()`.
- [ ] Incident updated to `RESOLVED` on success.
- [ ] Debt updated to `REPAID`.
**Verification:**
- [ ] Manual check: E2E test of F01 recovery.
**Dependencies:** Task 5
**Files likely touched:** `kavach/api/background.py`, `kavach/graph/safety.py`

## Checkpoint: Complete
- [ ] Full F01 lifecycle: Incident → Mitigation → Debt Created → Primary Recovers → Debt Repaid → Incident Resolved.

## Task 7: Create Alembic migration and SQLAlchemy model for `incident_memory` table.
**Description:** Define the `incident_memory` table schema (incident_id, fault_class, summary, repair_action, outcome, vector) in SQLAlchemy using pgvector and generate the Alembic migration.
**Acceptance criteria:**
- [x] SQLAlchemy model `IncidentMemory` is defined with a `vector` column of size matching `nomic-embed-text` (e.g., 768).
- [x] Alembic migration script is created and applies successfully.
**Verification:**
- [ ] Manual check: `uv run alembic upgrade head` runs without errors.
**Dependencies:** None
**Files likely touched:** `kavach/api/models.py`, `alembic/versions/xxx.py`

## Task 8: Implement Ollama embedding integration
**Description:** Create a client in `kavach/knowledge/embeddings.py` that calls the local Ollama instance (using `ollama` or raw `httpx`) to generate embeddings for a given text using `nomic-embed-text`.
**Acceptance criteria:**
- [x] Function `generate_embedding(text: str) -> list[float]` returns the vector.
- [x] Handles connection errors gracefully by falling back or returning None.
**Verification:**
- [x] Tests pass: Mocked test verifies the embedding function returns a list of floats.
**Dependencies:** None
**Files likely touched:** `kavach/knowledge/embeddings.py`, `tests/test_knowledge.py`

## Checkpoint: Foundation
- [x] Database migration runs successfully.
- [x] Embedding client function returns vectors.

## Task 9: Implement vector search retrieval and saving logic
**Description:** Write database logic to save an incident into the knowledge base and retrieve similar incidents using vector similarity (L2 distance or cosine similarity).
**Acceptance criteria:**
- [x] `save_incident_memory(session, ...)` saves a new record with an embedding.
- [x] `retrieve_similar_incidents(session, query_vector, limit=3)` returns the closest matches.
**Verification:**
- [x] Tests pass: Integration tests verify insertion and correct ordering on retrieval.
**Dependencies:** Task 7, Task 8
**Files likely touched:** `kavach/knowledge/store.py`, `kavach/knowledge/retrieval.py`, `tests/test_knowledge.py`

## Checkpoint: Storage
- [x] Unit tests pass for storage and similarity retrieval.

## Task 10: Update the Graph (`diagnose_node`) to retrieve similar incidents
**Description:** When a new incident comes in, embed the symptoms/context and retrieve similar past incidents. Add them to `state["evidence"]` for the RCA LLM to consider.
**Acceptance criteria:**
- [x] `diagnose_node.py` calls the retrieval function.
- [x] Retrieved incidents are added as `Evidence` objects to the state.
**Verification:**
- [x] Tests pass: Mocking the DB in `test_graph.py` shows evidence is populated.
**Dependencies:** Task 9
**Files likely touched:** `kavach/graph/nodes/diagnose.py`

## Task 11: Update the Graph to store the incident upon resolution
**Description:** When the incident is fully handled (e.g., in `verify_node` returning RESOLVED, or in a final node), create a summary of the fault and the repair and save it to the knowledge base.
**Acceptance criteria:**
- [x] Successful repairs are embedded and stored.
- [x] Unsuccessful hypotheses (failed repairs) are also optionally stored or marked differently.
**Verification:**
- [x] Tests pass: Graph execution correctly calls `save_incident_memory`.
**Dependencies:** Task 9
**Files likely touched:** `kavach/graph/nodes/verify.py` or similar end node.

## Checkpoint: Complete
- [x] E2E test shows that an incident is saved, and a subsequent identical incident pulls it as evidence.

## Task 12: Update `kavach/preflight/schema.py`
**Description:** Extract active roles from the manifest.
**Acceptance criteria:**
- [x] Method or property returns the set of roles.
**Verification:**
- [x] Manual check.
**Dependencies:** None

## Task 13: Update `kavach/catalogue/loader.py`
**Description:** Filter faults based on active roles.
**Acceptance criteria:**
- [x] `load_catalogue(roles=...)` filters correctly.
**Verification:**
- [x] Unit tests for loader.
**Dependencies:** Task 12

## Checkpoint: Core Logic
- [x] Loader correctly filters the catalogue.

## Task 14: Update `kavach/graph/nodes.py`
**Description:** Use the filtered catalogue during diagnosis.
**Acceptance criteria:**
- [x] `diagnose_node` passes `app_roles` to loader.
**Verification:**
- [x] E2E or graph tests.
**Dependencies:** Task 13

## Task 15: Update `kavach/preflight/checker.py`
**Description:** Report excluded faults during onboarding.
**Acceptance criteria:**
- [x] Output includes missing roles / excluded faults.
**Verification:**
- [x] `make onboard` shows the excluded roles.
**Dependencies:** Task 13

## Checkpoint: Complete
- [x] F-ROLE fully implemented.

## Task 16: Update `plan_node` for F-UNK
**Description:** Ensure empty plan for `INSUFFICIENT_EVIDENCE`.
**Acceptance criteria:**
- [x] `plan_node` returns empty plan when fault is unknown.
**Verification:**
- [x] Manual check of `nodes.py`.
**Dependencies:** None

## Task 17: Update `outcome_node` for F-UNK
**Description:** Ensure outcome is `ESCALATED`.
**Acceptance criteria:**
- [x] `outcome_node` handles unknown faults correctly.
**Verification:**
- [x] Manual check of `nodes.py`.
**Dependencies:** Task 16

## Task 18: Test Unknown Failure Path
**Description:** Write integration test for unknown failures.
**Acceptance criteria:**
- [x] Test proves `ESCALATED` outcome and zero actions.
**Verification:**
- [x] Test passes.
**Dependencies:** Task 17

## Checkpoint: Complete
- [x] F-UNK fully implemented.

## Task 19: Update `IncidentState` for F-SBX
**Description:** Add sandbox fields to state.
**Acceptance criteria:**
- [x] `sandbox_required` and `sandbox_passed` added to `state.py`.
**Verification:**
- [x] Manual check.
**Dependencies:** None

## Task 20: Update `plan_node` for F-SBX
**Description:** Check risk tier and set `sandbox_required`.
**Acceptance criteria:**
- [x] Sets `sandbox_required = True` for MEDIUM risk.
**Verification:**
- [x] Manual check of `nodes.py`.
**Dependencies:** Task 19

## Task 21: Implement Sandbox Nodes
**Description:** Add `sandbox_execute_node` and `sandbox_verify_node`.
**Acceptance criteria:**
- [x] Nodes exist and update state appropriately.
**Verification:**
- [x] Manual check of `nodes.py`.
**Dependencies:** Task 20

## Task 22: Update Graph Routing
**Description:** Wire the sandbox loop in `workflow.py`.
**Acceptance criteria:**
- [x] `gate` -> `sandbox_execute` -> `sandbox_verify` -> `execute` (if passed).
**Verification:**
- [x] Graph compiles.
**Dependencies:** Task 21

## Task 23: Test Sandbox Loop
**Description:** Write integration test for MEDIUM risk faults.
**Acceptance criteria:**
- [x] Test proves sandbox is executed and verified before real execution.
**Verification:**
- [x] Test passes.
**Dependencies:** Task 22

## Checkpoint: Complete
- [x] F-SBX fully implemented.

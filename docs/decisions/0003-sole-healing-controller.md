# ADR 0003 — Kavach is the sole self-healing controller; Kubernetes stays out

**Date:** 2026-10-02
**Status:** Accepted

## Context

The target repository already contains a partial self-healing mechanism, written before Kavach existed:

- `backend/aiops_agent.py` — a LangGraph `StateGraph` whose `heal_service` node calls `v1.delete_namespaced_pod()` on every pod matching a label
- `POST /v1/webhook/alert` — an **unauthenticated** route that invokes it, taking the service label and namespace straight from the request body
- `k8s/` — Deployment and Service manifests
- `docs/ADR-002-AIOps-and-Resilience.md` — which states that "true Self-Healing requires a Kubernetes control plane"

Two problems. First, against Kavach's requirements this mechanism is a **second writer** to the system under management, which breaks `FR-15a` (writer exclusivity) outright, and it satisfies none of Kavach's safety requirements: no allow-list, no risk tier, no inverse, no idempotency key, no pre-state witness. Second, standalone it is an unauthenticated remote pod-deletion primitive.

Third, and separately: the target's own accepted ADR asserts the opposite of Kavach's locked scope (ADR 0001) on Kubernetes.

## Decision

**In v1, Kavach is the only component permitted to mutate the system under management.**

| Artefact | Disposition |
|---|---|
| `backend/aiops_agent.py` | **Kept on disk** for historical and reference value. Not imported, not reachable, not executed |
| `POST /v1/webhook/alert` | **Removed from the running application.** The route is not registered |
| Pod deletion | **Unreachable.** No code path can invoke it |
| `k8s/` manifests | **Left on disk, unused by Kavach v1** |
| The target's `ADR-001` / `ADR-002` | **Not modified.** Kavach records its own position here instead |

This is option B of three considered. Option A (delete the file and its dependencies) is cleaner but discards a teammate's work and would require superseding the target's ADR. Option C (leave it active and document the conflict) was rejected: it leaves an unauthenticated pod-deletion endpoint reachable and a live `FR-15a` violation in the system.

**On Kubernetes, stated for reviewers:** the target repository contains Kubernetes manifests and a `kubernetes` client dependency. Kavach v1 does not support Kubernetes, does not read those manifests, and does not call the Kubernetes API. *"The target contains Kubernetes files"* and *"Kavach supports Kubernetes"* are different statements and only the first is true. `RuntimeAdapter` is the seam that would make a `K8sAdapter` additive later; the existing manifests are not a head start on it.

## Consequences

- **Positive:** one writer, one lock. `FR-15a` is satisfiable.
- **Positive:** an unauthenticated pod-deletion endpoint is removed from a running application. Worth doing on its own merits.
- **Positive:** the teammate's work survives in the repository and in history.
- **Negative:** the target carries dead code and unused manifests. Accepted — deleting them fights the target's own ADR for no functional gain.
- **Negative:** `langgraph`, `langchain` and `kubernetes` may remain in the target's image as now-unused dependencies. Not Kavach's concern to prune.
- **Risk:** a reviewer reading the target repo may cite its `ADR-002` as the project's position. `PRD.md` §5.3 is the document to cite in response, and `ROADMAP.md` keeps the target's ADRs out of agent context for the same reason.

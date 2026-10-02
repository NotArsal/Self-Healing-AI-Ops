# ADR 0001 — Locked scope for v1

**Date:** 2026-10-02
**Status:** Accepted

## Context

The original academic synopsis (`docs/synopsis-original.md`) targets "all types of AI systems" across nine layers, with Kubernetes, multi-cloud deployment, MongoDB, PyTorch and TensorFlow, predictive forecasting and reinforcement learning. That is a multi-year programme, not a one-semester project with a live demo, and published results show the hard parts are not solved: AIOpsLab's best agent reaches ~59% overall and mitigation sits near 43%; OpenRCA 2.0 reports 20.7% exact root-cause recovery across 11 frontier models.

Attempting the synopsis breadth produces nothing demonstrable. The project needs a narrow claim it can actually prove.

## Decision

Four constraints, binding until a superseding decision record exists.

1. **System under management:** one local `docker-compose` AI/RAG application. Not Kubernetes, not a cloud deploy API.
2. **Optimisation target:** a convincing live demo for review. Benchmark harness integration (AIOpsLab, RCAEval) is P2 stretch.
3. **Default mode:** `SIMULATION`, globally and for every newly onboarded project. See ADR 0006.
4. **Autonomy ceiling:** a project explicitly moved to `AUTONOMOUS` executes only LOW-risk actions. MEDIUM goes to sandbox-then-approval, HIGH to a human, `UNKNOWN` never auto-executes.

`PRD.md` §11 enumerates what is out of scope. Widening it requires a new file in this directory.

## Consequences

- **Positive:** the P0 feature set is 13 items over 7 injectable faults. Everything P1 and below can be cut and the demo still works.
- **Positive:** a bounded L4 claim ("full closed-loop autonomy over an enumerated catalogue") is defensible. "Self-healing for AI systems" is not.
- **Negative:** the delivered system is visibly narrower than the synopsis. This is addressed by stating the narrowing explicitly in the report rather than hoping nobody compares the two.
- **Negative:** Kubernetes being out of scope conflicts with the target repository's own `ADR-002`. Resolved in ADR 0003.

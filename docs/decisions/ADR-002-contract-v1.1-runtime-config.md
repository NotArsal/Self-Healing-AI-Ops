# ADR-002 — Contract v1.1: the `runtime_config` protocol and objective measurability

**Status:** accepted
**Date:** 2026-10-14
**Supersedes:** nothing. Amends `CONTRACT.md` v1 → v1.1.

---

## Context

Proof #2 (ROADMAP P9b) onboarded `targets/proof2` from `CONTRACT.md` alone and
logged five defects in `docs/decisions/proof2_defects.md`. Four of them shared a
single root cause: **the contract described what an application must declare, but
not enough for a platform to act on the declaration.**

- `reversible_state.kind: runtime_config` named a `read` and a `write` endpoint
  and stopped there. No method, no body shape. A platform cannot construct a
  mutation from that (defect #2).
- `permissions.allowed_actions` listed action names with no binding to the state
  they act on, so nothing connected `switch_model` to `model_selection`
  (defect #3).
- Consequently the executor had no way to realise any action against a live
  application and only supported `shell_command` (defect #4).
- Separately, an application could declare an objective the platform had no way
  to measure, and verification would skip it while still reporting a pass
  (defect #5, found while making F01 real).

Each of these forced a Kavach source change during onboarding, which is the
definition of a contract defect under §0.1.

## Decision

Amend the contract rather than special-case the application.

1. **Specify the `runtime_config` protocol** (`CONTRACT.md` §6.1): `GET` on
   `read` returning a JSON object containing `field`; idempotent `POST` on
   `write` with body `{"<field>": "<value>"}`; both reachable independently of
   application health.
2. **Add `field` and `values`** to a `runtime_config` declaration. `values` maps
   the platform's action vocabulary (`model_backup`) onto the application's
   (`backup`). Neither side adopts the other's spelling.
3. **Bind actions to state in the catalogue, not in code.** A catalogue action
   gains an optional `effect: {kind, key, value}` naming the `reversible_state`
   key it is realised through. The executor dispatches on that data; it never
   branches on an action's name.
4. **Require measurability** (`CONTRACT.md` §5.1): onboarding reports every
   declared metric it cannot measure, an unmeasurable objective never counts as
   satisfied, and onboarding captures a healthy baseline that deltas are
   measured against.

## Alternatives rejected

- **Hardcode an HTTP branch for `switch_model` in `execute_node`.** Smallest
  diff, and the option originally on the table. Rejected: it leaves defects #3
  and #4 open, adds the `elif action.name ==` chain `AGENTS.md` explicitly
  forbids, and the next fault class repeats the work. The defect log would record
  a problem we had chosen not to fix.
- **Make the application speak the platform's vocabulary** (accept
  `model_primary` at its admin endpoint). Rejected: it inverts the contract. The
  platform is supposed to adapt to the application, and requiring the
  application to change is the failure mode §0.1 measures.
- **Query Prometheus for objectives instead of probing.** Rejected in
  `ARCHITECTURE.md` §2.4 — it makes the healing loop depend on the metrics stack
  being up. Active probing keeps the loop self-sufficient at the cost of only
  supporting metrics that can be probed, which §5.1 now makes explicit rather
  than silent.

## Consequences

- `targets/proof2` is onboarded and heals F01 end to end with **zero Kavach
  source changes beyond those this ADR authorises**, which are contract
  implementations rather than per-application special cases.
- Adding a second `runtime_config`-backed action needs no Python: a catalogue
  `effect` block and a manifest declaration.
- Applications written against v1 that declared `runtime_config` without `field`
  are no longer conformant. This is a breaking change, hence the version bump.
  No such application exists outside this repository.
- Objectives whose metrics cannot be probed are now visibly unverified at
  onboarding instead of quietly unchecked. `proof2` declares none.

## Open

- `values` is a flat string map. A state whose value is structured (a config
  object rather than a scalar) is not expressible and is deferred to v2.
- Multi-metric objective categories are declarable but only the first metric per
  category is consumed. Noted in `from_manifest.py`.

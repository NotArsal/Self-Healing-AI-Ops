# ADR 0006 — `SIMULATION` is the default mode

**Date:** 2026-10-02
**Status:** Accepted

## Context

Earlier drafts stated the default mode three incompatible ways: `PRD.md` §5 said "`AUTONOMOUS` is the default mode"; `ARCHITECTURE.md` §10 said "`SIMULATION` ... as the default for any project not explicitly moved to `AUTONOMOUS`"; and the `kavach.yaml` example shipped `mode: AUTONOMOUS`.

The control plane mounts the Docker socket read-write. A wrong default here means a freshly onboarded project is eligible for automatic writes before anyone has reviewed its allow-list.

## Decision

**`SIMULATION` is the default — globally, and for every newly onboarded project.**

- A `kavach.yaml` that omits `mode` means `SIMULATION`.
- Moving a project to `APPROVAL` or `AUTONOMOUS` requires preflight to pass **and** an explicit per-project configuration change. Nothing does it implicitly.
- `AUTONOMOUS` then means: LOW executes automatically, MEDIUM goes to sandbox-then-approval, HIGH goes to a human, `UNKNOWN` never auto-executes.
- The mode check is present from the safety engine's first commit in P3, not added in P7. P7 adds `APPROVAL`'s interrupt/resume flow and the full tier routing, not the concept.

## Consequences

- **Positive:** the failure mode of a mistake is "Kavach did nothing", not "Kavach restarted something".
- **Positive:** the allow-list, which defaults to empty, and the mode, which defaults to `SIMULATION`, are two independent barriers that both have to be deliberately lowered.
- **Negative:** the demo requires an explicit mode switch, which is one more step to remember on stage. Mitigated by `UX-01` keeping the mode visible on every screen without scrolling, and by the mode switch into `AUTONOMOUS` listing exactly which actions become auto-executable.
- **Test:** `tests/test_healthz.py::test_default_mode_is_simulation` asserts the shipped default, so a regression fails the gate rather than being discovered on stage.

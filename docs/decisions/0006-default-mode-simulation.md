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

## Amendment — 2026-10-04

The decision stands; one claim in it did not survive contact with the build, and the phase number has changed.

- **Phase numbering.** "P3" and "P7" above are the old numbers. The safety engine is now **P6** (`ROADMAP.md` **Phase map** carries the full mapping). This record is not rewritten.
- **"The mode check is present from the safety engine's first commit" has not held, because there is no safety engine yet.** The `F06` closed loop (P2) and its RCA layer (P3) ship no mode parameter at all, so there is nothing to default. The shipped setting the test asserts is the configured default; it is not read by the loop, because no code reads it yet.
- **What actually constrains the loop today is narrower, and worth stating plainly:** it is invoked explicitly by a harness, never on a timer, so it cannot act unattended. That is a property of how it is called, not a guarantee enforced in code.
- **Therefore:** the mode check must land with `permit()` in P6, and it must land *before* anything invokes the loop automatically or a second repair action is added. Until then, "the default is `SIMULATION`" describes configuration, not behaviour, and must not be presented as a safety property in the report or the demo.

# ADR 0012 — The inverse of a generated patch is bytes, not `git revert`; and what promotion means

**Date:** 2026-10-19
**Status:** Accepted
**Supersedes:** `ARCHITECTURE.md` §6.2.1 constraint 3
**Related:** `0008-prompts-are-the-only-writable-path-into-the-target.md`, `0011-the-sandbox-and-apply-patch-are-restored.md`
**Required by:** `PRD.md` §5 — a change to a written constraint needs a decision record.

## Context

`ARCHITECTURE.md` §6.2.1 lists six constraints on `apply_patch`. Constraint 3
reads:

> **Git is the inverse.** The patch commits to an incident branch off
> `kavach/ops`; the pre-state blob SHA is the witness and `git revert` is the
> undo.

**That constraint cannot be implemented, and has not been implementable since
ADR 0008.** It is not a question of effort. Three binding rules each forbid it
independently:

1. **ADR 0008** established that the only writable path Kavach has into the
   target is the `prompts/` bind mount. Kavach does not have, and must not
   have, a checkout of the target it may commit to.
2. **`AGENTS.md` rule 10** forbids Kavach writing to `main` or to a working
   branch, forbids `git push` to any remote, forbids `--amend`, forbids
   force-pushing and forbids rewriting history. The target's `origin` is a
   teammate's repository.
3. **`ARCHITECTURE.md` §13** states the enforcement as *"No `git push` code
   path exists"*, and `executor/adapters/git.py` honours it by absence: the
   module exposes `check` and `apply` and contains no function that commits,
   branches, resets or pushes. A test asserts the absence.

An "incident branch off `kavach/ops`" in the target repository would require
all three to be false. Constraint 3 is a leftover from the earlier git
isolation model, written before ADR 0008 chose the mount.

The conflict became live because `apply_patch` now works: ADR 0011 records a
generated patch applied to a clone whose fast set then returned 100%. With a
repair that genuinely repairs, the question of how it is undone stops being
theoretical.

## Decision

### 1. The inverse is the pre-state bytes

`ApplyPatch.prepare()` reads the target file and keeps its exact contents.
`invert()` writes those bytes back. No model call, no git, no recomputation.

This is what `ARCHITECTURE.md` §6.0 asks for in general terms — *"the inverse
is deterministic data, never a model call... capture the pre-state witness; do
not re-derive it"* — and it is the same machinery `rollback_prompt` has had
proven in production since F07. Constraint 3 was the weaker form: `git revert`
derives the undo from history, which means the undo depends on the history
being intact and on a repository Kavach is not allowed to write to.

The witness is a SHA-256 digest of the prior contents rather than a git blob
SHA. It serves the same purpose - detecting that the file moved - without
requiring a repository.

### 2. Promotion: what a passing sandbox earns

`ARCHITECTURE.md` §6.2.1 constraint 4 says `permit()` returns
`REQUIRE_SANDBOX` unconditionally, and then **does not say what happens
next.** That gap is why nothing consumed the verdict: every path that was not
`ALLOW_AUTO` stopped and awaited, so a patch could never reach production
however many times a clone agreed.

Promotion requires **both** of:

- a human approval — an unapproved HIGH action returns `REQUIRE_APPROVAL` in
  every mode including `AUTONOMOUS`, so this is not bypassable by configuration;
- a sandbox run that **passed** — the action reports `sandbox_passed is True`.

The loop asks the ACTION, not its name. An action that ran no sandbox has no
such attribute, reads as `None`, and waits exactly as before. That matters
because `REQUIRE_SANDBOX` is also what every MEDIUM action receives in
`AUTONOMOUS`, where there is no approval behind it; a test asserts no other
action in the catalogue exposes the attribute.

Ordering, which is the whole point: the sandbox runs during `prepare()`,
BEFORE the gate and before any human is asked. Approving an untested diff is
not an approval, it is a signature.

## Consequences

- Constraint 3 in `ARCHITECTURE.md` §6.2.1 is superseded. The table should be
  read with this ADR beside it.
- Kavach still has no git write path of any kind into the target. Nothing in
  this ADR relaxes rule 10; it removes the one constraint that implied rule 10
  would have to be relaxed.
- The undo for a generated patch is identical in mechanism to `rollback_prompt`,
  which is a simplification: one witness-and-restore path, proven, instead of
  two.
- `apply_patch` is still absent from the target manifest's `allowed_actions`,
  so `permit()` denies it today. That line is deliberately left for the
  operator; see below.

## What is deliberately NOT done here

`apply_patch` has **not** been added to `allowed_actions` in the target's
`kavach.yaml`. Everything upstream of that line is built, tested and measured,
and the line is a single edit in the target repository.

It is left out for two reasons. The target is a separate, shared repository
and the project has been using "the target's working tree is clean" as
evidence of non-interference in every live run so far; editing it would spend
that signal. And enabling a model-authored write to a real application is the
operator's decision to make knowingly, not one to find already made.

To enable it, add to `allowed_actions` in the target's `kavach.yaml`:

```yaml
  # HIGH, and the only action whose content a model wrote. It cannot execute
  # unattended in any mode: an unapproved HIGH action returns
  # REQUIRE_APPROVAL even in AUTONOMOUS. A human approval plus a clone that
  # passed its fast set, and nothing less, writes this. The inverse is the
  # bytes read immediately before the write (ADR 0012).
  - apply_patch
```

# ADR 0009 — P7 is cut: no sandbox, no generated repair, no Laya, no knowledge base

**Date:** 2026-10-18
**Status:** Accepted
**Supersedes:** the P7 schedule in `ROADMAP.md`; the phase column for `F-SBX`, `F-CODE` and `F-DEC` in `PRD.md` §6
**Required by:** `PRD.md` §5, which makes scope binding and requires a decision record for a change to it.

## Context

Six of nine phases are complete. P6 is complete in substance: four fault
classes (`F01`, `F06`, `F07`, `F08`) each at 8 of 8 acceptance, with `F02`,
`F03` and `F05` dropped by `ROADMAP.md`'s own week-10 checkpoint and `F09`
closed on measurement (`PRD.md` §12).

P7 is four separate pieces of work: the full git-isolation model, the sandbox
(`F-SBX`), LLM-generated repairs (`F-CODE`/`apply_patch`), the Laya shadow
decision engine (`F-DEC`), and a pgvector knowledge base. **None of it is
started.**

P8 — measure, write, rehearse — is roughly a tenth done. The human baseline
has a protocol and an instrument but has not been run. The undo ablation has
not been run. `make bench` and `make scenario` are still stubs that `exit 1`.
There is no report and there are no slides.

The project is therefore much further along in **building** than in
**proving**, which `ROADMAP.md` P8 names in advance as *"the phase most teams
skip and most reviewers notice."*

## Decision

**P7 is cut in its entirety.** Nothing in it is attempted. The remaining
effort goes to P8.

This is a scope decision, not a discovery that the work is impossible. Each
piece was specified carefully and remains buildable; none of it is needed for
the claim this project makes.

## Why each piece is safe to cut

**The sandbox (`F-SBX`) and generated repair (`F-CODE`) are one decision, and
`ROADMAP.md` already says so.** Its P6 cut line records that `apply_patch`
cannot exist without somewhere survivable to try a model-authored diff first,
so cutting the sandbox cuts the patch with it. Both go. The approval path —
plan, risk tier, pre-state, inverse, human approves — is complete and proven
live without either.

**Laya (`F-DEC`) is shadow-only by design and never gates an action.**
`PRD.md` §7.1 is explicit that the deterministic rule engine is the decision
authority *permanently in v1*. Cutting the shadow removes a comparison, not a
capability: nothing Kavach does today consults it, and `permit()` is
forbidden from even reading it. The typed-decision frames are still logged
from P6 onward, so the fine-tuning corpus continues to accumulate at zero
cost and the work remains startable later.

**The knowledge base is an evidence enrichment, not a mechanism.** Diagnosis
runs on the live evidence frame; similar past incidents would improve it and
nothing depends on them.

**Git isolation is partially moot.** The one action that writes files,
`rollback_prompt`, writes the working tree directly and never touches git —
see `ADR 0008`, which also explains why mounting the repository to reach
`.git` would demote `AGENTS.md` rule 10 from structural to procedural. With
`apply_patch` cut, no remaining action needs an incident branch.

## Consequences

**The safety rules do not relax.** Rule 10 stands, the deny-list stands,
`permit()` is unchanged, and the executor still has exactly one writable path
into the target (`prompts/`). Cutting features removes capability; it must
not remove a guard, and it does not.

**Documents must stop implying these exist.** This is the real risk of a cut,
and `PRD.md` §12 already names it: *"Aspiration diagrams drifting into
capability claims… Fabricated results in a report. The worst outcome
available to this project."* Every place that describes a P7 feature in the
present tense is now a claim about software that will not exist. `ROADMAP.md`
P7, the `PRD.md` §6 feature table, `ARCHITECTURE.md`'s decision-engine and
`apply_patch` sections, and `AGENTS.md`'s Laya section are all marked **CUT**
rather than deleted — deleting them would lose the reasoning, and the
reasoning is worth keeping for anyone continuing the work.

**`executor/catalogue.py`'s note that `apply_patch` "registers in P7" is now
wrong** and is corrected to say it is unregistered and unbuilt. The action
remains absent from the registry, which is the behaviour that matters: an
unregistered action cannot be authorised by `permit()` whatever a document
says.

**The report must state the cut and its reason.** A reviewer asking "why no
sandbox?" should meet a decision, not a gap. The honest framing is that four
fault classes proven end to end with a deterministic cross-check — including
one behaviourally identical pair that separates only on which artifact
drifted — is a stronger result than five classes plus three half-built
subsystems.

**What this buys.** Every remaining hour goes to P8: the human baseline, the
undo ablation (`PRD.md` §10.3 calls reproducing STRATUS's ablation shape the
strongest available research contribution), the conditional metrics, a demo
script that runs clean three times, and the report. These convert work
already done into a defensible result; P7 would have added work with no
evidence attached to it.

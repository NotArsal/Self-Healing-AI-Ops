# ADR 0008 — `prompts/` is the only writable path Kavach has into the target

**Date:** 2026-10-17
**Status:** Accepted
**Required by:** `AGENTS.md` security rules, which make the control plane's reach into the target a safety property rather than a configuration detail.

## Context

Until F07, every action Kavach could perform wrote through the target's validated HTTP config interface. `rollback_config` and `switch_llm_endpoint` both `PUT /v1/admin/config`, which refuses denied keys, unknown keys and out-of-range values, and applies all-or-nothing. The api container mounted exactly one file of the target's repository:

```yaml
- ${TARGET_REPO}/kavach.yaml:/app/target/kavach.yaml:ro
```

with the comment *"one file rather than the repository: Kavach reads the target's safety policy and must never be able to widen it."* The control plane had no write access to the target's filesystem at all.

F07 is a prompt version regression. Its repair has to get known-good prompt text back onto disk, and prompts are not reachable through the config interface: `control_interface.settable` lists six scalar keys, and the target exposes no endpoint that returns or accepts prompt text.

`ROADMAP.md` recorded the intended mechanism as *"needs the git adapter extended to prompt blobs"*. That was re-examined and rejected before being built, for two reasons given below.

## Decision

The api container mounts the target's `prompts/` directory, and only that directory, read-write:

```yaml
- ${TARGET_REPO}/prompts:/app/target/prompts
```

The known-good text comes from `Baseline.prompt_contents`, captured on the host by `make onboard` and read back through the existing read-only `harness/baselines/` mount. `executor/prompt_rollback.py` is the only module that writes it, and it refuses any name that is not a bare `*.txt` resolving inside that directory.

## Why not git, which the roadmap called for

**The git framing assumes HEAD is the known-good version, and for this fault class it usually is not.** A working-tree injector leaves HEAD clean, so git would work for the demo. A real prompt regression arrives *as a commit* — someone edits a prompt, commits it, and quality falls — in which case HEAD **is** the bad version and a git rollback restores nothing. The mechanism would have demonstrated well and worked rarely.

**Mounting the repository to reach `.git` would demote the project's strongest safety guarantee.** `AGENTS.md` rule 10 says the executor never pushes, never amends, never force-pushes and never touches `main` or the user's working branch. That rule is currently *structural*: the api container does not have the repository, so it cannot do any of those things whatever its code says. Mounting `${TARGET_REPO}` read-write to reach the git database would make every one of those guarantees *procedural* — true only for as long as no code path does it. Buying that for one fault class is a bad trade, and it is the kind of trade that is invisible once made.

A third option — adding `/v1/admin/prompts` to the target so prompts flow through the same audited interface as everything else — was considered and rejected as a twelfth permitted addition (`PRD.md` §5.2 caps the list at eleven, and ADR 0007 took the eleventh). It remains the right answer if the target ever gains a prompt-management surface for its own reasons.

## Consequences

**The blast radius is two text files**, `answer.txt` and `query_expansion.txt`, totalling about 1 KB. Nothing else in the target's repository is reachable from the api container: not `.git`, not `docker-compose.yml`, not `backend/`, not the corpus.

**The repair needs no restart, and that is a property of the target, not of this decision.** `prompts_loader` reads each prompt per request with no cache, deliberately, so that a revert "takes effect without a rebuild or restart". A prompt repair that required `docker restart` would be a restart's blast radius wearing a prompt's clothes.

**Verification asks the target, not the filesystem.** `verify_applied` compares against the digests the *running backend* computes from the directory it is actually reading, never against a re-hash of the file Kavach just wrote. Re-hashing would prove only that the write succeeded, which is never the thing in doubt; what is in doubt is whether the container sees it. The same check runs at capture time — `_capture_prompts` refuses to record text whose digest the target does not report — and at injection time, so a control plane pointed at the wrong directory fails loudly at all three points rather than silently repairing nothing.

**A baseline captured before this change cannot repair F07.** It records prompt digests without the text, and a digest identifies a file without being able to restore one. The detector reports that case as `INSUFFICIENT_EVIDENCE` naming `make onboard`, rather than claiming a fault whose repair would fail at `prepare()` on every attempt.

**`prompt_contents` puts the target's prompt text in the baseline artifacts.** These are already gitignored working files under `harness/baselines/`; prompts are not secrets, and `AGENTS.md`'s rule is about credentials. Worth noting, not worth guarding.

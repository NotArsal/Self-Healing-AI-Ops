# ADR 0033 — One second read when the first finds too little

**Date:** 2026-11-21
**Status:** Accepted by the owner 2026-11-21 ("write fix now, deploy later"). Written and tested; **not yet deployed**. Deploying it needs an image rebuild, and that waits until the night bench's replacement runs have finished, so those runs measure the same code as the runs they replace.
Tests: `tests/test_f02_loop.py` §4 (4). Against the loop without this change, the night-bench case and the fail-closed case fail; the two "does not wait" cases pass either way, as they should.
**Related:** [ADR 0026](0026-detection-asks-the-fast-set-at-once-verification-does-not.md)

## Context

In the larger-corpus night bench (2026-11-20/21, round 5, F02), the model
diagnosed F02 correctly and the validator approved the failover. Before acting
on an approved plan, the loop detects again. That second detection returned
INSUFFICIENT_EVIDENCE on "0.0 generation calls completed in the window", and
Kavach escalated without acting. It failed safe, but a correct heal was lost.

F02's detector needs at least one completed generation in its 2-minute window
(`latency_degradation.py`, `min_generations`), because a slow call is only
counted when it ends. Prometheus reads it from the target every 15s
(`infra/prometheus.yml`). In that run:

| UTC | |
|---|---|
| 04:05:09 | first run's fast set ends (3 calls, ~85s each, ADR 0026) |
| 04:05:34 | plan approved; the re-check starts its own fast set |
| 04:07:05 | re-check reads Prometheus. Its own 3 calls end now, unscraped. The first run's are ~116s old, and the sample before them has left the window: `increase(...[2m])` = 0 |
| 04:07:30 | the re-check's calls appear in Prometheus |

The gap between the two reads decides it. Across the four F02 runs of that
bench it was 94s and 99s when Groq diagnosed (healed), and 115s and 116s when
the Gemini backup did, after Groq failed (one healed, one lost). The same ~85s
fast set appears on the paper corpus (82–86s on 2026-11-12), so the larger
corpus is not the cause: the margin was always thin.

## Decision

Detection reads its signals once, as before. If that read is
INSUFFICIENT_EVIDENCE **and** the fast set failed, the loop waits
`SECOND_READ_AFTER_S` (20s: the 15s scrape interval plus 5s for the scrape to
land) and reads once more. The second read is the verdict. The first is kept
in the incident as `detection.first_read`, and the wait is announced on the
event stream as a `detect` `info` event.

- **Only then.** A run that detects at once (F07, F08: ~14s) or a passing fast
  set never waits, so the <30s MTTD target is not touched for them.
- **Once.** A second INSUFFICIENT_EVIDENCE escalates exactly as before.
- **Same rules.** The second read goes through the same `run_all`, with the
  same fast-set result. It cannot make a failing set healthy, and if two
  detectors claim on it, it escalates. Note what this does include: a first
  read that was ambiguous (two claims) also gets the second read, and if only
  one detector claims on that read, the loop proceeds on it, exactly as it
  would had that been the first read. Nothing is decided on the first read's
  evidence plus the second's; each read stands alone.

## Rejected

- **Always wait.** It would add 20s to every detection, and push F07 and F08
  from ~14s to ~34s, past the 30s target.
- **A longer window.** `latency_degradation.py` already explains why 2m and not
  5m: residue from an earlier slowdown would be blamed on a later F07 or F08.

## Consequences

- An undiagnosed failing run escalates ~20s later than before.
- The second read can end only in a single claimed fault or an escalation. The
  fast set is not re-run, and a failing set can never produce NO_FAULT
  (`run_all`), so the wait cannot talk the loop into calling a broken system
  healthy.
- **To prove before claiming it works:** a fresh F02 bench after deploying,
  ideally with the backup provider forced, so that the 115s gap is the normal
  case rather than a coincidence.

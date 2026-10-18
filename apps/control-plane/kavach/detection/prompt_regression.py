"""F07 prompt version regression — deterministic detection.

No LLM. Every signal is a comparison between the prompt digests the running
target reports and the digests the baseline capture recorded, or a boolean
from the fast-verification set, and the same inputs always produce the same
verdict.

THIS FAULT NEEDED NO SEAM CHANGE, WHICH IS THE POINT OF HAVING BUILT ONE
F08 forced `Signals` into existence because a config hash is not a Prometheus
series. F07's signal is not a Prometheus series either — it is
`prompt_version.files` from the target's control interface, compared against
`prompt_version.files` in the baseline — and both of those already arrive in
`Signals.client` and `Signals.baseline`. `ROADMAP.md` P6 asks that a new fault
class change nothing in the core; this one adds a module and a registration
line, and the widening F08 paid for is what makes that true.

WHY IT CANNOT COLLIDE WITH F08
F08 claims on drift in `settings`, compared by key against the baseline
snapshot. A prompt edit moves no setting: the target computes `config_hash`
from `runtime_config` alone and reports `prompt_version` separately, so an
F07 injection leaves F08's entire input identical to baseline and F08 returns
NO_FAULT on it. The two classes read disjoint halves of one endpoint's
response, so the ownership argument `config_regression.CLAIMED_ELSEWHERE`
makes between F08 and F06 is not needed here — the separation is structural.

WHY IT CANNOT COLLIDE WITH F01 OR F06, AND THE ONE CASE THAT IS NOT STRUCTURAL
F01 requires a high `llm_error_ratio`; a prompt regression leaves the endpoint
entirely healthy, so F01 stays quiet. F06 is the one that needs care. A
sufficiently destructive prompt edit could produce answers with no Sources
block, which is one of the three things the fast set checks and reads like
lost grounding — but F06 claims on RETRIEVAL metrics (`kept_chunks`,
`empty_context_ratio`), not on the shape of the answer, and a prompt cannot
move those: retrieval has already happened by the time the prompt is rendered.
So the two are separable in evidence. They are not separable by construction,
and an injector that degrades the prompt until retrieval metrics move would
break that — which is why `harness/faults/f07_prompt_regression.py` asserts
grounding is intact after injecting.

DRIFT ALONE IS NOT A FAULT — THE SAME HALF OF PRD §6 F08 LEANS ON
Someone editing a prompt is the normal way this application is improved. With
the fast set passing, a changed prompt is reported as NO_FAULT with the
changed files named in the evidence, and nothing is written. Rolling an
author's deliberate edit back because it is merely *different* would be the
control plane overruling its own owner, and for prompts that is a more
obviously wrong thing to do than it is for config.

WHAT A DIGEST CANNOT DO
A digest proves a file changed. It cannot say how, cannot say whether the new
text is worse, and cannot be rolled back to. That is why this detector claims
only in conjunction with a failing fast set (the "worse" half comes from
behaviour, not from the hash) and why `Baseline.prompt_contents` exists at all
(the "roll back to" half comes from recorded bytes). A baseline holding
digests but no text can detect F07 and cannot repair it; `collect` reports
that case rather than letting the loop discover it at prepare() time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kavach.detection.base import (
    Detection,
    DetectorSpec,
    Evidence,
    Readings,
    Signals,
    Verdict,
)

__all__ = [
    "FAULT_CLASS", "FAULT_NAME", "SERVICE", "SPEC",
    "Thresholds", "collect", "evaluate",
]

FAULT_CLASS = "F07"
FAULT_NAME = "prompt_regression"
SERVICE = "backend"


@dataclass(frozen=True)
class Thresholds:
    """Only one, and it is a presence check rather than a level."""

    # A changed prompt is a changed prompt; there is no magnitude to threshold.
    min_changed_files: int = 1


def _changed(live: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Files whose reported digest differs from the captured one.

    Only files present in BOTH are compared. A prompt the baseline never
    recorded cannot be rolled back to anything, so reporting it as a
    regression would propose a repair with no target. A prompt that has been
    DELETED since capture is reported separately by `collect`, because that is
    a different failure with a different fix.
    """
    return {
        name: {"baseline": baseline[name], "live": live[name]}
        for name in baseline
        if name in live and live[name] != baseline[name]
    }


def collect(signals: Signals) -> Readings:
    """Read the live prompt digests and compare them with the capture.

    Returns missing rather than raising when either source is absent: the
    offline tests drive detectors with no client, and a detector that cannot
    read its own inputs must report INSUFFICIENT_EVIDENCE.
    """
    baseline_pv = dict(signals.baseline.get("prompt_version") or {})
    baseline_files = dict(baseline_pv.get("files") or {})
    # The recorded TEXT, which is what makes the fault repairable. Absent in
    # any baseline captured before `prompt_contents` was added.
    captured_text = dict(signals.baseline.get("prompt_contents") or {})

    live_files: dict[str, Any] = {}
    if signals.client is not None:
        try:
            cfg = signals.client.config()
            live_files = dict((cfg.get("prompt_version") or {}).get("files") or {})
        except Exception:
            # An unreachable control interface is missing evidence, not an
            # unchanged prompt set. Saying "nothing changed" here would clear
            # a system this detector cannot see.
            live_files = {}

    if not baseline_files or not live_files:
        return {
            "baseline_files": baseline_files or None,
            "live_files": live_files or None,
            "changed": None,
            "vanished": None,
            "repairable": None,
        }

    changed = _changed(live_files, baseline_files)
    return {
        "baseline_files": baseline_files,
        "live_files": live_files,
        "changed": changed,
        # Captured, then gone. Not a regression — the file the target reads is
        # missing, and writing text back is not obviously the right fix.
        "vanished": sorted(set(baseline_files) - set(live_files)),
        # Can every changed file actually be restored? A detector that claims
        # a fault whose repair cannot be built escalates every time, which is
        # worse for an operator than being told the baseline is incomplete.
        "repairable": sorted(n for n in changed if n not in captured_text) == [],
    }


def evaluate(
    readings: Readings,
    fast_set_passed: bool,
    fast_set_pass_rate: float,
    thresholds: Thresholds | None = None,
) -> Detection:
    """Decide from the prompt comparison and the fast-set outcome. Pure."""
    t = thresholds or Thresholds()
    ev: list[Evidence] = []
    reasons: list[str] = []

    changed = readings.get("changed")
    vanished = readings.get("vanished")
    repairable = readings.get("repairable")

    ev.append(Evidence(
        kind="fast_verification",
        source="kavach/verification/fast_set.yaml",
        value=f"{fast_set_pass_rate:.0%} pass",
        expected="100% pass",
        supports_fault=not fast_set_passed,
    ))

    if changed is None:
        reasons.append(
            "cannot compare prompts: the baseline capture records no prompt "
            "digests, or the target's control interface could not be read. "
            "This is missing evidence, not an unchanged prompt set"
        )
        ev.append(Evidence("prompt_comparison", "baseline + control interface",
                           None, "both readable", False))
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    ev.append(Evidence(
        kind="prompt_version",
        source="target /v1/admin/config vs baseline capture",
        value=changed or "every prompt matches the captured digest",
        expected="no prompt file differs from the captured known-good",
        supports_fault=bool(changed),
    ))
    if vanished:
        ev.append(Evidence(
            kind="prompt_missing",
            source="baseline capture",
            value=vanished,
            expected="every captured prompt is still reported by the target",
            supports_fault=False,
        ))

    # --- the decision
    if not changed:
        if vanished:
            reasons.append(
                f"no prompt's content changed, but the target no longer "
                f"reports {vanished}. A prompt that has disappeared is not a "
                f"version regression and writing text back is not obviously "
                f"the right fix"
            )
            return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev,
                             reasons=reasons)
        reasons.append("every prompt file matches its captured digest")
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    # A changed prompt on a working system is an author at work, not a fault.
    if fast_set_passed:
        reasons.append(
            f"{len(changed)} prompt file(s) differ from the captured baseline "
            f"({sorted(changed)}) but the fast set passes, so nothing is "
            f"broken. Reported, not repaired: editing a prompt is how this "
            f"application is improved, and rolling an author's work back "
            f"because it is merely different would be the control plane "
            f"overruling its own owner"
        )
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    if len(changed) < t.min_changed_files:  # pragma: no cover - unreachable at 1
        reasons.append("no prompt changed by enough files to claim")
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    if not repairable:
        ev.append(Evidence(
            kind="baseline_completeness",
            source="baseline capture prompt_contents",
            value="digests only",
            expected="the known-good TEXT of every captured prompt",
            supports_fault=False,
        ))
        reasons.append(
            f"{len(changed)} prompt file(s) changed ({sorted(changed)}) and "
            f"the fast set is failing, but the baseline records digests "
            f"without the text, so there is nothing to roll back TO. A digest "
            f"identifies a file; it cannot restore one. Re-run `make onboard` "
            f"to capture prompt_contents. Escalating rather than claiming a "
            f"fault whose repair cannot be built"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    reasons.append(
        f"{len(changed)} prompt file(s) differ from the captured known-good "
        f"({sorted(changed)}) and the fast set is failing. The prompt is the "
        f"instruction the model follows, and the captured text is recorded, "
        f"so the repair is a rollback to it"
    )
    reasons.append("the fast set confirms the user-visible symptom")
    return Detection(
        verdict=Verdict.FAULT,
        fault_class=FAULT_CLASS,
        fault_name=FAULT_NAME,
        service=SERVICE,
        evidence=ev,
        reasons=reasons,
        # Deliberately None, unlike F08. `loop.py` reserves `repair_target`
        # for a value only detection can know; the known-good prompt text is
        # on disk in the baseline and the directory is declared in the
        # manifest, so it arrives through `repair_values()` and this detector
        # stays free of filesystem knowledge.
        repair_target=None,
    )


SPEC = DetectorSpec(
    fault_class=FAULT_CLASS,
    fault_name=FAULT_NAME,
    service=SERVICE,
    collect=collect,
    evaluate=evaluate,
    repair_action="rollback_prompt",
)

"""F08 config / environment regression — deterministic detection.

No LLM. Every signal is a comparison between the live control-interface
settings and the baseline capture on disk, or a boolean from the
fast-verification set, and the same inputs always produce the same verdict.

THE SIGNAL IS NOT A METRIC, WHICH IS WHY THE SEAM HAD TO WIDEN
`PRD.md` §6 defines this class as "config hash changed + SLO breach within the
window". A config hash is not a Prometheus series: it comes from the target's
own control interface, and the known-good value comes from the baseline
`make onboard` captured. `detection/base.py`'s `Signals` object exists because
of this detector — see its docstring.

THE DISCRIMINATOR THAT MATTERS, AND IT IS OWNERSHIP, NOT THRESHOLDS
Every other config-driven fault is ALSO a config change. Injecting `F06`
moves `rerank_threshold`, which moves the config hash, so "hash changed + fast
set failing" is true during an `F06` as well. A detector that claimed on that
alone would collide with `F06` on every single retrieval collapse, and
`run_all()` would refuse to choose between them - which is what happened the
first time `F01` and `F06` both claimed.

So this detector does not ask *whether* config changed. It asks WHICH KEY
changed, and claims only when the drifted keys are ones no more specific class
owns:

    rerank_threshold   -> F06 owns it (retrieval collapse)
    llm_base_url       -> F01 and F02 own it (endpoint outage / latency)

    anything else      -> F08. A setting moved, nobody else explains it, and
                          the known-good value is recorded, so the repair is a
                          rollback to that value.

`CLAIMED_ELSEWHERE` is therefore load-bearing, not documentation. A key added
to the control interface without being listed here or owned by a new detector
becomes F08's by default, which is the correct default for a residual class:
unexplained config drift is exactly what F08 is for.

WHY THE FAST SET IS REQUIRED, NOT OPTIONAL
Config drift on its own is not a fault. An operator may have changed a setting
deliberately, and Kavach rolling that back unasked would be the control plane
fighting its own owner. `PRD.md`'s wording is "config hash changed AND SLO
breach" - both halves. Drift with the fast set passing is reported as
NO_FAULT with the drift named in the evidence, so a human can see it without
anything being written.

NOT MEASURED YET
The injected value below is chosen, not swept, and the module says so rather
than implying a measurement. `max_tokens` is clamped to 16 because `rag.py`
passes it straight to Ollama and a 16-token answer cannot contain any of the
fast set's keywords - the answer is truncated before the figure appears, while
retrieval, grounding and the endpoint all stay healthy. That gives this class
a signature nothing else in the catalogue produces. What is NOT established is
the boundary: the largest clamp that still fails all three cases. `F09` is the
phase that forces a token sweep, and this constant should be re-derived there.
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
    "CLAIMED_ELSEWHERE", "FAULT_CLASS", "FAULT_NAME", "SERVICE", "SPEC",
    "Thresholds", "collect", "evaluate",
]

FAULT_CLASS = "F08"
FAULT_NAME = "config_regression"
SERVICE = "backend"

# Settings a MORE SPECIFIC fault class owns. Drift in these is not F08, and
# claiming it would collide with the detector that does own it.
CLAIMED_ELSEWHERE: frozenset[str] = frozenset({
    "rerank_threshold",   # F06 retrieval collapse
    "llm_base_url",       # F01 endpoint outage, F02 latency degradation
})


@dataclass(frozen=True)
class Thresholds:
    """Only one, and it is a presence check rather than a level."""

    # A drifted key is a drifted key; there is no magnitude to threshold.
    min_drifted_keys: int = 1


def _drift(live: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Keys whose live value differs from the captured one, with both values.

    Only keys present in BOTH are compared. A key the baseline never recorded
    cannot be rolled back to anything, so reporting it as drift would propose
    a repair with no target.
    """
    return {
        key: {"baseline": baseline[key], "live": live[key]}
        for key in baseline
        if key in live and live[key] != baseline[key]
    }


def collect(signals: Signals) -> Readings:
    """Read the live config and compare it with the baseline capture.

    Returns missing rather than raising when either source is absent: the
    offline tests drive detectors with no client, and a detector that cannot
    read its own inputs must report INSUFFICIENT_EVIDENCE.
    """
    baseline_settings = dict(signals.baseline.get("settings") or {})
    baseline_hash = str(signals.baseline.get("config_hash") or "")

    live_settings: dict[str, Any] = {}
    live_hash = ""
    if signals.client is not None:
        try:
            live_settings = dict(signals.client.settings())
            live_hash = str(signals.client.config_hash())
        except Exception:
            # An unreachable control interface is missing evidence, not zero
            # drift. Saying "nothing changed" here would clear a system this
            # detector cannot see.
            live_settings, live_hash = {}, ""

    if not baseline_settings or not live_settings:
        return {
            "baseline_settings": baseline_settings or None,
            "live_settings": live_settings or None,
            "baseline_config_hash": baseline_hash or None,
            "live_config_hash": live_hash or None,
            "drift": None,
            "unclaimed_drift": None,
        }

    drift = _drift(live_settings, baseline_settings)
    unclaimed = {k: v for k, v in drift.items() if k not in CLAIMED_ELSEWHERE}
    return {
        "baseline_settings": baseline_settings,
        "live_settings": live_settings,
        "baseline_config_hash": baseline_hash,
        "live_config_hash": live_hash,
        "drift": drift,
        "unclaimed_drift": unclaimed,
    }


def evaluate(
    readings: Readings,
    fast_set_passed: bool,
    fast_set_pass_rate: float,
    thresholds: Thresholds | None = None,
) -> Detection:
    """Decide from the config comparison and the fast-set outcome. Pure."""
    t = thresholds or Thresholds()
    ev: list[Evidence] = []
    reasons: list[str] = []

    drift = readings.get("drift")
    unclaimed = readings.get("unclaimed_drift")
    baseline_hash = readings.get("baseline_config_hash")
    live_hash = readings.get("live_config_hash")

    ev.append(Evidence(
        kind="fast_verification",
        source="kavach/verification/fast_set.yaml",
        value=f"{fast_set_pass_rate:.0%} pass",
        expected="100% pass",
        supports_fault=not fast_set_passed,
    ))

    if drift is None or unclaimed is None:
        reasons.append(
            "cannot compare config: the baseline capture has no settings "
            "snapshot, or the target's control interface could not be read. "
            "This is missing evidence, not an absence of drift"
        )
        ev.append(Evidence("config_comparison", "baseline + control interface",
                           None, "both readable", False))
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    ev.append(Evidence(
        kind="config_hash",
        source="target /v1/admin/config vs baseline capture",
        value=f"{live_hash} (baseline {baseline_hash})",
        expected="unchanged from the captured known-good",
        supports_fault=bool(live_hash and live_hash != baseline_hash),
    ))
    ev.append(Evidence(
        kind="config_drift",
        source="live settings vs baseline settings",
        value=drift or "none",
        expected="no setting differs from the captured known-good",
        supports_fault=bool(drift),
    ))
    if drift:
        claimed = sorted(set(drift) & CLAIMED_ELSEWHERE)
        if claimed:
            ev.append(Evidence(
                kind="drift_owned_elsewhere",
                source="detection/config_regression.py CLAIMED_ELSEWHERE",
                value=claimed,
                expected="no drift in keys a more specific class owns",
                supports_fault=False,
            ))

    # --- the decision
    if not drift:
        reasons.append("every setting matches the captured known-good value")
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    # Drift with a working system is information, not a fault. An operator may
    # have changed a setting on purpose, and rolling that back unasked would be
    # the control plane overruling its own owner.
    if fast_set_passed:
        reasons.append(
            f"{len(drift)} setting(s) differ from the captured baseline "
            f"({sorted(drift)}) but the fast set passes, so nothing is broken. "
            f"Reported, not repaired: a deliberate operator change must not be "
            f"rolled back because it is merely different"
        )
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    if len(unclaimed) < t.min_drifted_keys:
        reasons.append(
            f"the fast set failed and config drifted, but every drifted key is "
            f"owned by a more specific fault class ({sorted(drift)}). That "
            f"class's detector explains this, and claiming it here would make "
            f"two detectors fight over one incident"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    reasons.append(
        f"{len(unclaimed)} setting(s) drifted from the captured known-good "
        f"({sorted(unclaimed)}) and the fast set is failing, with no more "
        f"specific class owning them. The known-good value is recorded, so the "
        f"repair is a rollback to it"
    )
    reasons.append("the fast set confirms the user-visible symptom")
    return Detection(
        verdict=Verdict.FAULT,
        fault_class=FAULT_CLASS,
        fault_name=FAULT_NAME,
        service=SERVICE,
        evidence=ev,
        reasons=reasons,
        # Exactly the keys this detector claimed, at their CAPTURED values -
        # not the whole baseline. Rolling back a key no fault involved would
        # overrule a deliberate operator change.
        repair_target={k: v["baseline"] for k, v in unclaimed.items()},
    )


SPEC = DetectorSpec(
    fault_class=FAULT_CLASS,
    fault_name=FAULT_NAME,
    service=SERVICE,
    collect=collect,
    evaluate=evaluate,
    # Same action as F06 and the same risk tier, because it is the same
    # mechanism: restore a recorded known-good value through the validated
    # config interface. MEDIUM because it changes application behaviour
    # (ARCHITECTURE.md §6.2).
    repair_action="rollback_config",
)

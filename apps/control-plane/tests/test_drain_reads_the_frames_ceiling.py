"""The harness must drain to the number the RCA frame states, not another one.

THE BUG THIS PINS, found 2026-11-02 by a demo rehearsal failing twice.

`drain()` waited for `llm_error_ratio` to fall below the F01 DETECTOR's firing
threshold, 0.50 - "half of all calls failing is not noise". The RCA frame
tells the model the healthy expectation is `< 0.20`. So the drain declared the
system clean at 0.2697, and the frame then handed the model that same number
labelled abnormal: a second anomaly beside the real config regression. The
model drifted to its F06 attractor, `deterministic_agreement` refused it, and
act 2 of `make scenario` escalated instead of parking for approval - twice,
looking like a Kavach defect when it was a harness precondition.

The two numbers answer different questions and both are correct:
  0.50 - is this an endpoint outage worth repairing?
  0.20 - is this value worth putting in front of the model as abnormal?

Borrowing one for the other is the error. This file fails if anyone borrows
again, or if the stated expectation and the constant drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kavach.detection.endpoint_outage import (  # noqa: E402
    Thresholds as F01Thresholds,
)
from kavach.rca.evidence import (  # noqa: E402
    FRAME_ERROR_RATIO_CEILING,
    HEALTHY_EXPECTATION,
)


def test_the_constant_and_the_prose_the_model_reads_agree() -> None:
    """The expectation string is prompt text. If the constant changes, the
    sentence the model reads has to change with it - and `:.2f` matters,
    because a bare float renders as "0.2" and silently edits the prompt."""
    stated = HEALTHY_EXPECTATION["llm_error_ratio"]
    assert stated == "< 0.20 (measured healthy 0.0)", (
        f"the llm_error_ratio expectation the model reads is now {stated!r}; "
        "this is prompt text and every RCA measurement in the report was "
        "taken against the previous wording")
    assert f"< {FRAME_ERROR_RATIO_CEILING:.2f}" in stated


def test_the_frame_ceiling_is_not_the_detectors_firing_threshold() -> None:
    """Documented as a test because the two were conflated once already.

    Should they ever legitimately become equal, this fails and whoever made
    them equal has to say so deliberately rather than inherit it.
    """
    assert F01Thresholds().error_ratio_floor > FRAME_ERROR_RATIO_CEILING, (
        "the frame's 'worth mentioning' ceiling must be STRICTER than the "
        "detector's 'this is an outage' threshold; if it is not, draining to "
        "the frame's number no longer guarantees a clean frame")


def test_the_drain_waits_on_the_frame_ceiling() -> None:
    """The regression itself: `drain()` must compare against the frame's
    constant. Asserted on the source rather than by running a drain, which
    needs a live target, Prometheus and several minutes."""
    src = (ROOT / "harness" / "kavach_baseline.py").read_text(encoding="utf-8")
    body = src.split("def drain(")[1].split("\ndef ")[0]
    assert "FRAME_ERROR_RATIO_CEILING" in body, (
        "drain() no longer compares llm_error_ratio against the RCA frame's "
        "ceiling; act 2 of `make scenario` will start failing again")
    assert "error_ratio_floor" not in body, (
        "drain() is reading the F01 detector's firing threshold again - that "
        "is the 2026-11-02 bug exactly")

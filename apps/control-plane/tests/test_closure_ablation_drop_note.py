"""The detector-drop log entry records the detector's reasons, not only its verdict.

EXPERIMENT_CLOSURE_ABLATION.md section 31.8. No network, no target, no model.
"""

from __future__ import annotations

from harness.closure_ablation import detector_drop_note
from kavach.detection import base as det


def test_a_drop_records_why_the_detector_disagreed() -> None:
    d = det.Detection(verdict=det.Verdict.INSUFFICIENT_EVIDENCE,
                      reasons=["prompt hash unchanged", "error ratio 0.01 < 0.20"])
    note = detector_drop_note("F07", 2, d)
    assert note.startswith("F07#2: detector said INSUFFICIENT_EVIDENCE")
    assert "prompt hash unchanged; error ratio 0.01 < 0.20" in note


def test_a_misattribution_names_the_class_it_chose() -> None:
    d = det.Detection(verdict=det.Verdict.FAULT, fault_class="F01", reasons=["x"])
    assert "detector said F01," in detector_drop_note("F06", 1, d)


def test_reasons_are_capped_so_one_drop_cannot_flood_the_artifact() -> None:
    d = det.Detection(verdict=det.Verdict.NO_FAULT,
                      reasons=["r" * 500, "b", "c", "never shown"])
    note = detector_drop_note("F08", 3, d)
    assert "r" * 120 in note and "r" * 121 not in note
    assert "never shown" not in note


def test_no_reasons_says_so_rather_than_printing_nothing() -> None:
    d = det.Detection(verdict=det.Verdict.NO_FAULT)
    assert note_end(detector_drop_note("F08", 4, d)) == "detector reasons: none recorded"


def note_end(note: str) -> str:
    return note[note.index("detector reasons:"):]

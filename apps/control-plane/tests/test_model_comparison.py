"""The model comparison replays stored frames exactly, samples fairly, and
counts the one number that must stay zero."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.model_comparison import (  # noqa: E402
    CLASSES,
    detection_of,
    frame_of,
    sample,
    score,
)
from kavach.detection import base as det  # noqa: E402
from kavach.rca.evidence import EvidenceFrame  # noqa: E402


def test_a_stored_frame_rebuilds_exactly() -> None:
    frame = EvidenceFrame(collected_at="2026-11-12T09:00:00+00:00", problems=["p"])
    frame.add(eid="EV-M06", kind="metric", name="llm_error_ratio", value=0.0,
              expected="< 0.20")
    frame.add(eid="EV-C04", kind="config", name="max_tokens", value=2, note="DIFFERS")
    assert frame_of(frame.to_dict()).to_dict() == frame.to_dict()
    assert frame_of(frame.to_dict()).render() == frame.render()


def test_a_stored_detection_rebuilds_exactly() -> None:
    d = det.Detection(verdict=det.Verdict.FAULT, fault_class="F08",
                      fault_name="Configuration regression", service="backend",
                      reasons=["r"], evidence=[det.Evidence(
                          kind="config", source="EV-C04", value=2, expected="0",
                          supports_fault=True)])
    assert detection_of(d.to_dict()).to_dict() == d.to_dict()


def test_the_sample_is_stratified_and_the_same_every_time() -> None:
    frames = {f"INC-{fc}-{n}": fc for fc in CLASSES for n in range(10)}
    first = sample(frames, 3)
    assert first == sample(frames, 3)
    assert sorted(frames[i] for i in first) == sorted(list(CLASSES) * 3)


def row(truth: str, cls: str | None, approved: bool, **kw: Any) -> dict[str, Any]:
    return {"truth": truth, "class": cls, "answered": cls is not None,
            "correct": cls == truth, "approved": approved, "latency_s": 1.0,
            "model": "m", "live_model": kw.get("live_model"),
            "live_class": kw.get("live_class")}


def test_a_wrong_diagnosis_the_gate_approved_is_counted_as_unsafe() -> None:
    s = score([row("F08", "F08", True), row("F08", "F06", True),
               row("F06", "F08", False), row("F01", None, False),
               row("F07", "F07", False, live_model="m", live_class="F07")])
    assert (s["correct"], s["wrong"], s["no_answer"]) == (2, 2, 1)
    assert s["unsafe_approved_wrong"] == 1
    assert s["wrong_caught_by_gate"] == 1
    assert s["right_but_refused"] == 1
    assert s["replay_agrees_with_live"] == "1/1"


def test_a_row_from_another_day_under_a_reused_id_is_not_used() -> None:
    from harness.model_comparison import matches

    bench = {"injected": "F08", "det_class": "F08", "llm_class": "F08"}
    same = {"deterministic": {"fault_class": "F08"}, "diagnosis": {"fault_class": "F08"}}
    other_day = {"deterministic": {"fault_class": "F06"}, "diagnosis": {"fault_class": "F06"}}
    assert matches(same, bench)
    assert not matches(other_day, bench)


def test_a_busy_provider_is_not_scored_as_the_models_answer() -> None:
    """Gemini's 503s and the laptop's Wi-Fi drops are retried, not recorded;
    a model's own invalid output (Groq's HTTP 400) is its answer."""
    from harness.model_comparison import transient

    assert transient("LLM call failed: gemini returned HTTP 503: overloaded")
    assert transient("groq returned HTTP 429: rate limit")
    assert transient("<urlopen error [Errno -3] Temporary failure in name resolution>")
    assert not transient('groq returned HTTP 400: {"code":"json_validate_failed"}')
    assert not transient("model returned text that is not JSON despite a schema constraint")
    assert not transient("")


def test_a_retry_asks_only_frames_whose_latest_real_answer_was_none() -> None:
    """`--retry-no-answer-from`: a later real answer clears a frame, and a busy
    provider's row neither adds nor clears one."""
    from harness.model_comparison import no_answer_frames

    def line(iid: str, answered: bool, error: str = "") -> str:
        import json
        return json.dumps({"provider": "groq", "model": "m", "incident_id": iid,
                           "answered": answered, "error": error})

    assert no_answer_frames([
        line("A", False, "groq returned HTTP 400: json_validate_failed"),
        line("B", False, "not JSON"), line("B", True),
        line("C", True), line("C", False, "groq returned HTTP 503: busy"),
        line("D", False, "gemini returned HTTP 503: overloaded"),
    ]) == {("groq:m", "A")}

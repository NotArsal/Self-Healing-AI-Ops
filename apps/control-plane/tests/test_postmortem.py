"""The postmortem renderer.

The renderer must not become a press release. Most of these tests are
about a failed incident reading as a failed incident, because a tool that
writes up only its wins is marketing and the refusals are where this
project's argument lives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kavach.audit.log import AuditLog
from kavach.audit.postmortem import render


def an_incident(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "incident_id": "INC-1",
        "project": "simple-rag",
        "detected_at": "2026-10-19T01:00:00+00:00",
        "resolved_at": "2026-10-19T01:01:24+00:00",
        "status": "RESOLVED",
        "fault_class": "F07",
        "service": "backend",
        "diagnosed_by": "deterministic",
        "detection": {"verdict": "FAULT", "detail": "fast set 0%"},
        "rca": {"fault_class": "F07", "confidence": 0.9,
                "evidence_ids": ["EV-C08", "EV-V00"], "outcome": "ACCEPTED"},
        "planned_action": "rollback_prompt",
        "decision": {"verdict": "ALLOW_AUTO", "risk_tier": "MEDIUM",
                     "mode": "AUTONOMOUS", "reasons": ["within blast radius"]},
        "action": {"risk_tier": "MEDIUM",
                   "requested_settings": {"answer.txt": "aaa"},
                   "inverse_settings": {"answer.txt": "bbb"},
                   "executed": True, "reverted": False},
        "verification": {"before": {"pass_rate": 0.0, "passed": False},
                         "after": {"pass_rate": 1.0, "passed": True}},
        "corpus_before": {"chunks": 30.0},
        "corpus_after": {"chunks": 30.0},
        "outcome": "healed by rollback_prompt",
        "escalation_reason": "",
    }
    base.update(over)
    return base


# --- the happy path reads correctly ----------------------------------------


def test_it_reports_the_shape_of_a_successful_heal() -> None:
    md = render(an_incident())
    assert "# Incident INC-1 — RESOLVED" in md
    assert "healed by rollback_prompt" in md
    assert "84.0s" in md, "detected-to-resolved was not computed"
    assert "0% (fail)" in md and "100% (pass)" in md


def test_the_inverse_is_shown_even_when_it_was_never_needed() -> None:
    """How a reader checks the recoverability claim instead of taking it on
    trust. The undo existing and not being used is the normal case."""
    md = render(an_incident())
    assert "Inverse held" in md
    assert "bbb" in md


def test_the_corpus_is_reported_as_unchanged() -> None:
    md = render(an_incident())
    assert "Corpus unchanged: **yes**" in md


# --- the failures must read as failures ------------------------------------


def test_an_escalated_incident_says_so_prominently() -> None:
    md = render(an_incident(
        status="ESCALATED", outcome="escalated without acting",
        escalation_reason="denied by the safety engine: not allow-listed"))
    assert "ESCALATED" in md
    assert "**Escalated:** denied by the safety engine" in md


def test_a_sandbox_refusal_is_recorded_not_omitted() -> None:
    """The most informative result this project has produced: a patch that
    passed all six deterministic checks and still failed on a clone."""
    md = render(an_incident(
        status="ESCALATED",
        planned_action="apply_patch",
        action={"risk_tier": "HIGH", "requested_settings": {},
                "inverse_settings": {"prompts/answer.txt": "ccc"},
                "executed": False, "reverted": False,
                "sandbox_trial": {"passed": False,
                                  "detail": "sandbox fast set 67% (fail)"}},
        outcome="refused after its sandbox run"))
    assert "sandbox fast set 67% (fail)" in md
    assert "Executed: **no**" in md


def test_a_corpus_that_moved_is_flagged_loudly() -> None:
    md = render(an_incident(corpus_after={"chunks": 12.0}))
    assert "Corpus unchanged: **NO**" in md


def test_an_incident_that_wrote_nothing_says_nothing_was_written() -> None:
    md = render(an_incident(action={}, planned_action=None))
    assert "Nothing was written." in md


# --- it reports what is missing rather than inventing it -------------------


def test_a_missing_timestamp_is_an_em_dash_not_a_guess() -> None:
    md = render(an_incident(resolved_at=""))
    assert "**Detected to resolved:** —" in md


def test_without_an_audit_log_integrity_is_not_claimed() -> None:
    """A postmortem that asserted the chain was intact without checking
    would be worse than one that omits the claim."""
    md = render(an_incident())
    assert "integrity is **not claimed**" in md
    assert "Hash chain intact" not in md


# --- the chain is verified, not assumed ------------------------------------


def test_the_chain_is_verified_and_the_answer_is_printed(
    tmp_path: Path,
) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("detect", incident_id="INC-1", detail="fast set 0%")
    log.append("gate", incident_id="INC-1", verdict="ALLOW_AUTO")
    log.append("execute", incident_id="INC-2", detail="another incident")

    md = render(an_incident(), audit=log)
    assert "Hash chain intact: **yes**" in md
    assert "Rows for this incident: 2 of 3" in md, (
        "rows must be filtered to this incident but counted against the log"
    )
    assert "another incident" not in md


def test_a_tampered_chain_is_reported_in_the_document(
    tmp_path: Path,
) -> None:
    """THE test. If tampering could produce a clean postmortem, the
    postmortem would be worth nothing."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("detect", incident_id="INC-1", detail="fast set 0%")
    log.append("execute", incident_id="INC-1", detail="wrote the repair")

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("fast set 0%", "fast set 99%")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    md = render(an_incident(), audit=log)
    assert "Hash chain intact: **NO**" in md
    assert "First break at row" in md


def test_the_patch_is_quoted_when_a_model_wrote_one() -> None:
    diff = ("--- a/prompts/answer.txt\n+++ b/prompts/answer.txt\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n")
    md = render(an_incident(
        planned_action="apply_patch",
        action={"risk_tier": "HIGH", "requested_settings": {},
                "inverse_settings": {}, "executed": True, "reverted": False,
                "diff": diff}))
    assert "```diff" in md
    assert "+new" in md


def test_the_evidence_frame_is_included_when_supplied() -> None:
    md = render(an_incident(), evidence="EV-M01 similarity 0.21\nEV-V00 0%")
    assert "EV-M01 similarity 0.21" in md

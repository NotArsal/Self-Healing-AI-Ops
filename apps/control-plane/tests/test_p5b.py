"""Persistence, approval and the mode switch.

Zero network: `IncidentStore` is exercised without a database, because its
contract is that an unavailable store degrades rather than blocking. If these
tests needed Postgres they would be testing the wrong thing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kavach import loop
from kavach.api import routes
from kavach.api.runner import (
    LoopRunner,
    NoBaselineError,
    NotAwaitingError,
    policy_from_manifest,
)
from kavach.config import Settings
from kavach.db.store import IncidentStore, sync_url
from kavach.onboarding.manifest import Manifest

MANIFEST: dict[str, Any] = {
    "apiVersion": "kavach/v1",
    "project": {
        "name": "simple-rag",
        "compose_file": "docker-compose.yml",
        "compose_project": "target_rag-app",
        "git": {"base_branch": "modernize-stack"},
    },
    "services": {"backend": {"role": "api"}, "db": {"role": "database"}},
    "slo": [{
        "name": "x", "expression": "sum(rate(a_total[5m])) or vector(0)",
        "comparator": "<", "threshold": 0.1, "window_s": 300,
    }],
    "verification": {"fast": {"set": "kavach/verification/fast_set.yaml"}},
    "allowed_actions": ["rollback_config"],
    # The validator requires the full unconditional set; a manifest that lists
    # fewer is rejected, which is the behaviour this fixture originally broke.
    "denied_mutations": [
        "embed_model_change", "data_delete", "database_drop",
        "scale_to_zero", "migration",
    ],
    "mode": "APPROVAL",
    "confidence_threshold": 0.75,
}


def a_runner(tmp_path: Path) -> LoopRunner:
    return LoopRunner(Settings(kavach_root=str(tmp_path)))


# --- the manifest IS the safety posture -------------------------------------


def test_policy_comes_from_the_manifest() -> None:
    policy = policy_from_manifest(Manifest.model_validate(MANIFEST))
    assert policy.name == "simple-rag"
    assert policy.compose_project == "target_rag-app"
    assert policy.services == frozenset({"backend", "db"})
    assert policy.allowed_actions == frozenset({"rollback_config"})
    assert "embed_model_change" in policy.denied_mutations
    assert policy.mode == "APPROVAL"
    assert policy.confidence_threshold == 0.75


def test_a_mode_override_beats_the_file_without_rewriting_it() -> None:
    manifest = Manifest.model_validate(MANIFEST)
    overridden = policy_from_manifest(manifest, mode_override="AUTONOMOUS")
    assert overridden.mode == "AUTONOMOUS"
    assert manifest.mode == "APPROVAL", "the manifest is not mutated"


def test_the_override_cannot_widen_the_allow_list() -> None:
    """A mode change is not a licence. Only the manifest lists actions."""
    policy = policy_from_manifest(
        Manifest.model_validate(MANIFEST), mode_override="AUTONOMOUS"
    )
    assert policy.allowed_actions == frozenset({"rollback_config"})
    assert "embed_model_change" in policy.denied_mutations


@pytest.mark.target_repo
def test_set_mode_is_audited(tmp_path: Path) -> None:
    """An unrecorded move to AUTONOMOUS is indistinguishable from a compromise."""
    runner = a_runner(tmp_path)
    runner.set_mode("AUTONOMOUS")
    events = [r["event"] for r in runner.audit.rows()]
    assert "mode_change" in events
    row = next(r for r in runner.audit.rows() if r["event"] == "mode_change")
    assert row["mode"] == "AUTONOMOUS"
    assert row["actor"] == "operator"
    assert runner.audit.verify().intact


# --- the store degrades, it does not block ----------------------------------


def test_an_unavailable_store_never_raises(tmp_path: Path) -> None:
    """The priority that matters: bookkeeping must not stop a repair."""
    store = IncidentStore(
        "postgresql+psycopg://nobody@127.0.0.1:1/none", connect_timeout=2
    )
    assert store.init() is False
    assert store.available() is False
    assert store.unavailable_reason

    # Every method is safe to call anyway.
    store.save({"incident_id": "INC-1", "status": "RESOLVED"})
    store.save_decision("INC-1", {"verdict": "ALLOW_AUTO"})
    store.save_hypotheses("INC-1", [{"rank": 1, "description": "x"}])
    assert store.get("INC-1") is None
    assert store.recent() == []
    assert store.with_status("AWAITING_APPROVAL") == []
    assert store.hypotheses("INC-1") == []
    assert store.fleet_metrics()["available"] is False


def test_a_runner_does_not_connect_when_constructed(tmp_path: Path) -> None:
    """A constructor that opens a socket makes every test wait on a database."""
    runner = a_runner(tmp_path)
    assert runner.store.available() is False


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("postgresql+asyncpg://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql+psycopg://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
    ],
)
def test_the_configured_driver_is_corrected(configured: str, expected: str) -> None:
    """Compose still supplies +asyncpg from Phase 0; the loop is synchronous."""
    assert sync_url(configured) == expected


def test_fleet_metrics_report_null_not_zero_when_empty(tmp_path: Path) -> None:
    """A zero MTTR reads as "instant", which is the opposite of "no data"."""
    metrics = a_runner(tmp_path).fleet_metrics()
    assert metrics["mttr_seconds"] is None
    assert metrics["repair_success_rate"] is None
    assert metrics["incidents"] == 0


# --- approval ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_an_incident_that_is_not_parked_is_refused(
    tmp_path: Path,
) -> None:
    runner = a_runner(tmp_path)
    with pytest.raises(NotAwaitingError, match="not awaiting approval"):
        await runner.approve("INC-nope")


def test_rejecting_an_incident_that_is_not_parked_is_refused(tmp_path: Path) -> None:
    runner = a_runner(tmp_path)
    with pytest.raises(NotAwaitingError):
        runner.reject("INC-nope", "no thanks")


def test_a_rejection_requires_a_reason(tmp_path: Path) -> None:
    """A rejection without one teaches nobody anything."""
    runner = a_runner(tmp_path)
    runner._awaiting["INC-1"] = {}
    with pytest.raises(ValueError, match="needs a reason"):
        runner.reject("INC-1", "   ")
    # Three spaces pass the API's length rule; refusing them must not cost
    # the plan, or the incident can be neither approved nor rejected.
    assert "INC-1" in runner.awaiting()


def test_a_rejection_is_recorded_and_escalates(tmp_path: Path) -> None:
    runner = a_runner(tmp_path)
    inc = loop.Incident(incident_id="INC-1", project="simple-rag")
    inc.status = loop.IncidentStatus.AWAITING
    runner._remember(inc)
    runner._awaiting["INC-1"] = {}

    runner.reject("INC-1", "the threshold change looks deliberate")

    stored = runner.incident("INC-1")
    assert stored is not None
    assert stored.status is loop.IncidentStatus.ESCALATED
    assert "rejected by operator" in stored.escalation_reason
    row = next(r for r in runner.audit.rows() if r["event"] == "rejected")
    assert row["reason"] == "the threshold change looks deliberate"
    assert "INC-1" not in runner.awaiting()


def _plan(incident_id: str = "INC-1") -> loop.ApprovedPlan:
    return loop.ApprovedPlan(
        incident_id=incident_id, fault_class="F06", service="backend",
        action="rollback_config", requested_settings={"rerank_threshold": 0.35},
        rca={}, diagnosed_by="deterministic")


@pytest.mark.asyncio
async def test_approve_hands_the_parked_plan_to_the_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0025: the approval carries the plan the operator saw, not just an id."""
    runner = a_runner(tmp_path)
    runner._awaiting["INC-1"] = {"plan": _plan(), "use_rca": False}
    seen: dict[str, Any] = {}

    async def start(use_rca: bool = True,
                    approved: loop.ApprovedPlan | None = None) -> loop.Incident:
        seen.update(use_rca=use_rca, approved=approved)
        return loop.Incident(incident_id="INC-2", project="p")

    monkeypatch.setattr(runner, "start", start)
    await runner.approve("INC-1")

    assert seen == {"use_rca": False, "approved": _plan()}
    row = next(r for r in runner.audit.rows() if r["event"] == "approved")
    assert row["plan"]["action"] == "rollback_config"


def _parked_runner(tmp_path: Path) -> LoopRunner:
    runner = a_runner(tmp_path)
    inc = loop.Incident(incident_id="INC-1", project="simple-rag")
    inc.status = loop.IncidentStatus.AWAITING
    runner._remember(inc)
    runner._awaiting["INC-1"] = {"plan": _plan(), "use_rca": False}
    return runner


@pytest.mark.asyncio
async def test_an_approved_incident_stops_awaiting_and_names_its_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It read AWAITING_APPROVAL forever, so the console kept offering an
    Approve button that could only fail."""
    runner = _parked_runner(tmp_path)

    async def start(use_rca: bool = True,
                    approved: loop.ApprovedPlan | None = None) -> loop.Incident:
        return loop.Incident(incident_id="INC-2", project="p")

    monkeypatch.setattr(runner, "start", start)
    await runner.approve("INC-1")

    old = runner.incident("INC-1")
    assert old is not None
    assert old.status is loop.IncidentStatus.APPROVED
    assert "INC-2" in old.outcome
    assert routes.incident_out(old).awaiting_approval is False


@pytest.mark.asyncio
async def test_an_approval_whose_rerun_cannot_start_stays_parked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan is removed before the re-run starts, and a refused start
    used to take the approval with it."""
    runner = _parked_runner(tmp_path)

    async def start(use_rca: bool = True,
                    approved: loop.ApprovedPlan | None = None) -> loop.Incident:
        raise NoBaselineError("the manifest could not be read")

    monkeypatch.setattr(runner, "start", start)
    with pytest.raises(NoBaselineError):
        await runner.approve("INC-1")

    assert "INC-1" in runner.awaiting()
    old = runner.incident("INC-1")
    assert old is not None
    assert old.status is loop.IncidentStatus.AWAITING
    assert any(r["event"] == "approval_not_run" for r in runner.audit.rows())


@pytest.mark.asyncio
async def test_a_parked_run_records_the_plan_it_parked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without this there is nothing for an approval to bind to."""
    import asyncio

    from kavach.safety.engine import ProjectPolicy

    runner = a_runner(tmp_path)

    def run_once(*_: Any, incident_id: str = "", **__: Any) -> loop.Incident:
        return loop.Incident(
            incident_id=incident_id, project="p",
            status=loop.IncidentStatus.AWAITING, fault_class="F06",
            service="backend", planned_action="rollback_config",
            diagnosed_by="deterministic",
            action={"requested_settings": {"rerank_threshold": 0.35}})

    monkeypatch.setattr(loop, "run_once", run_once)
    monkeypatch.setattr(runner, "baseline", lambda: (0.35, "test"))
    monkeypatch.setattr(runner, "baseline_doc", lambda: {})
    monkeypatch.setattr(runner, "repair_values", lambda: {})
    monkeypatch.setattr(runner, "fast_set_path", lambda: tmp_path / "unused.yaml")
    monkeypatch.setattr(runner, "policy",
                        lambda: ProjectPolicy(name="p", compose_project="c"))

    inc = await runner.start(use_rca=False)
    for _ in range(500):
        if not runner._running:
            break
        await asyncio.sleep(0.01)

    assert runner._awaiting[inc.incident_id]["plan"] == _plan(inc.incident_id)

    # A plan waiting for a person is not a failure. The console drew this
    # event as a red cross and the Loop Ring as a failed stage, at the very
    # moment the operator was meant to read the plan and approve it.
    from kavach.api.events import bus

    await asyncio.sleep(0.05)  # publish_threadsafe lands on the loop
    resolved = [e for e in bus.replay()
                if e.get("incident_id") == inc.incident_id and e["stage"] == "resolve"]
    assert [e["status"] for e in resolved] == ["info"]


def test_a_parked_incident_is_listed_until_it_is_decided(tmp_path: Path) -> None:
    runner = a_runner(tmp_path)
    runner._awaiting["INC-1"] = {}
    assert runner.awaiting() == ["INC-1"]
    inc = loop.Incident(incident_id="INC-1", project="p")
    runner._remember(inc)
    runner.reject("INC-1", "not now")
    assert runner.awaiting() == []


# --- the AWAITING outcome ---------------------------------------------------


def test_awaiting_is_distinct_from_both_success_and_escalation() -> None:
    """A plan exists and nothing was written. That is its own outcome."""
    # mypy proves the identity comparisons statically, so assert the things
    # that can actually regress: the wire value, and that `resolved` stays
    # false for a plan that was never executed.
    assert str(loop.IncidentStatus.AWAITING) == "AWAITING_APPROVAL"
    assert len({str(s) for s in loop.IncidentStatus}) == len(list(loop.IncidentStatus))

    inc = loop.Incident(incident_id="INC-1", project="p")
    inc.status = loop.IncidentStatus.AWAITING
    assert inc.resolved is False
    assert inc.to_dict()["status"] == "AWAITING_APPROVAL"

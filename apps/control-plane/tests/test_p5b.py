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
from kavach.api.runner import (
    LoopRunner,
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

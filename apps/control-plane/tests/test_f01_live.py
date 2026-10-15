"""F01 against a live application.

These tests run the real proof2 service over real HTTP on the port its
kavach.yaml declares. Nothing here is simulated: the adapter writes to the app,
the probes measure the app, and the undo is asserted by reading the app back.
"""

import asyncio
import importlib.util
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import uvicorn

from kavach.catalogue.loader import load_catalogue
from kavach.detection.monitor import build_incident_scenario, detect_breach
from kavach.graph.nodes import execute_node, unwind_node
from kavach.graph.state import IncidentState
from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.remediation.runtime_config import apply_effect, read_value, revert_effect
from kavach.scenarios.from_manifest import load_target
from kavach.tnr.models import Action
from kavach.verification.baseline import baseline_path, save_baseline
from kavach.verification.live import measure_eval_pass_rate, measure_objectives

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF2_DIR = REPO_ROOT / "targets" / "proof2"
MANIFEST = PROOF2_DIR / "kavach.yaml"
# The manifest hardcodes this port; the app must be reachable where it declares.
PORT = 8080
BASE = f"http://localhost:{PORT}"


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def proof2_app():
    """Run the real proof2 service for the duration of this module."""
    if not _port_is_free(PORT):
        # Deliberately a failure, not a skip: pytest exits 0 on an all-skipped
        # run, so `make test-integration` would report success having asserted
        # nothing about the live loop.
        pytest.fail(
            f"port {PORT} is in use, so the live target cannot start. Stop "
            f"`make target-up` (or whatever holds {PORT}) and re-run."
        )

    spec = importlib.util.spec_from_file_location("proof2_main", PROOF2_DIR / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    server = uvicorn.Server(
        uvicorn.Config(module.app, host="127.0.0.1", port=PORT, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        pytest.fail("proof2 did not become healthy")

    yield module

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def stub_shadow_laya(monkeypatch):
    """Laya is shadow-only and cannot change a verdict, so stub it.

    Left real, each gate call runs a local transformer inference; the unwind loop
    alone does four, which dominated the runtime of this file without asserting
    anything. tests/test_debt.py stubs it the same way.
    """
    from kavach.remediation.tnr_gate import SafetyAssessment

    monkeypatch.setattr(
        "kavach.remediation.tnr_gate.evaluate_safety",
        lambda action, context: SafetyAssessment(is_safe=True, reason="stubbed"),
    )


@pytest.fixture(autouse=True)
def reset_target(proof2_app):
    """Every test starts from a healthy app on the primary model."""
    proof2_app.state.update(
        {"provider_primary_down": False, "api_down": False, "active_model": "primary"}
    )
    yield
    proof2_app.state.update(
        {"provider_primary_down": False, "api_down": False, "active_model": "primary"}
    )
    baseline_path(MANIFEST).unlink(missing_ok=True)


@pytest.fixture
def target(proof2_app):
    return load_target(MANIFEST)


@pytest.fixture
def healthy_baseline(target):
    """Capture the baseline while the app is healthy, as onboarding would."""
    save_baseline(MANIFEST, measure_objectives(target))
    return target


def _switch_to_backup_binding(target):
    effect = load_catalogue().actions["switch_model"].effect
    assert effect is not None, "switch_model must declare a live effect"
    rs_def = (target.manifest.reversible_state or {})["model_selection"]
    return effect, rs_def


# --- the adapter's inverse, which the whole rollback guarantee rests on ---


def test_inverse_restores_prior_state(target) -> None:
    effect, rs_def = _switch_to_backup_binding(target)
    action = Action(name="switch_model", params={"target": "model_backup"})

    assert read_value(rs_def) == "primary"

    record = apply_effect(effect, action, rs_def, mode="AUTONOMOUS")

    assert record.applied is True
    assert read_value(rs_def) == "backup", "the live app must have actually changed"
    assert record.pre_state_witness == {"model_selection": "primary"}

    revert_effect(effect, record, rs_def, mode="AUTONOMOUS")

    assert read_value(rs_def) == "primary", "the inverse must restore the prior state"


def test_inverse_is_built_from_the_witness_not_the_declared_fallback(target) -> None:
    """If the app was somewhere unexpected, the undo goes back to where it was."""
    effect, rs_def = _switch_to_backup_binding(target)
    # Arrive to find the app already on backup, contradicting the declared fallback.
    httpx.post(f"{BASE}/v1/admin/model", json={"model": "backup"}, timeout=5)

    action = Action(
        name="switch_model",
        params={"target": "model_backup", "fallback": "model_primary"},
    )
    record = apply_effect(effect, action, rs_def, mode="AUTONOMOUS")

    assert record.pre_state_witness == {"model_selection": "backup"}
    assert record.inverse_action.params["target"] == "model_backup"


def test_simulation_mode_writes_nothing(target) -> None:
    effect, rs_def = _switch_to_backup_binding(target)
    action = Action(name="switch_model", params={"target": "model_backup"})

    record = apply_effect(effect, action, rs_def, mode="SIMULATION")

    assert record.applied is False
    assert read_value(rs_def) == "primary", "SIMULATION must produce zero side effects"
    assert record.pre_state_witness == {"model_selection": "primary"}


# --- measurement is real ---


def test_golden_set_measures_real_degradation(target) -> None:
    assert measure_eval_pass_rate(target) == 1.0

    httpx.post(f"{BASE}/v1/admin/model", json={"model": "backup"}, timeout=5)

    degraded = measure_eval_pass_rate(target)
    assert degraded == pytest.approx(0.90), (
        "the backup model must measurably answer worse; this number is scored "
        "from real responses, not derived from a threshold"
    )


def test_detect_breach_sees_the_injected_outage(target, proof2_app) -> None:
    assert detect_breach(target) is None, "a healthy app must not raise an incident"

    httpx.post(f"{BASE}/inject/F01", timeout=5)

    breach = detect_breach(target)
    assert breach is not None
    assert "availability" in breach.breached
    assert breach.measured["availability"] == 1.0
    assert breach.health["llm-proxy"] == "unhealthy"
    assert breach.health["api"] == "healthy"


def test_detection_evidence_cites_what_was_measured(target) -> None:
    httpx.post(f"{BASE}/inject/F01", timeout=5)
    breach = detect_breach(target)
    assert breach is not None

    scenario = build_incident_scenario(target, breach, scenario_id="inc-test")

    assert scenario.target is not None
    ids = {e.id for e in scenario.evidence or []}
    assert "ev-objective-availability" in ids
    assert "ev-health-llm-proxy" in ids
    # Detection must not pre-empt diagnosis.
    assert scenario.fault_class == "UNKNOWN"


# --- the loop, end to end, against the live app ---


@patch("kavach.graph.nodes.analyze_root_cause")
def test_f01_heals_end_to_end_with_real_deltas(mock_rca, healthy_baseline, proof2_app) -> None:
    """Inject, detect, diagnose, repair, verify -- with no human and no fiction."""
    mock_rca.return_value = RCAResponse(
        fault_class="F01",
        confidence=0.95,
        evidence_ids=["ev-objective-availability", "ev-health-llm-proxy"],
        rejected_alternatives=["F02"],
    )
    target = healthy_baseline

    httpx.post(f"{BASE}/inject/F01", timeout=5)
    breach = detect_breach(target)
    assert breach is not None

    scenario = build_incident_scenario(target, breach, scenario_id="inc-live-f01")
    result = build_workflow().invoke(
        IncidentState(
            incident_id="inc-live-f01",
            scenario=scenario,
            mode="AUTONOMOUS",
            simulation_state={},
        )
    )

    assert result["gate_verdict"] == "ALLOW"
    assert result["risk_tier"] == "LOW"
    assert result["verification_passed"] is True
    # Primary is still down; the system routed around it rather than fixing it.
    assert result["outcome"] == "MITIGATED"

    assert read_value(
        (target.manifest.reversible_state or {})["model_selection"]
    ) == "backup", "the live application must actually be on the backup model"

    deltas = result["verification_deltas"]
    assert deltas["availability"] == pytest.approx(0.0), "errors back to baseline"
    assert deltas["quality"] == pytest.approx(-0.10), (
        "quality is genuinely worse than the healthy baseline, measured by "
        "running the golden set against the backup model"
    )


@patch("kavach.graph.nodes.verify_live")
@patch("kavach.graph.nodes.analyze_root_cause")
def test_verification_failure_unwinds_the_live_app(
    mock_rca, mock_verify, healthy_baseline, proof2_app
) -> None:
    """A failed repair must put the real application back where it was."""
    mock_rca.return_value = RCAResponse(
        fault_class="F01", confidence=0.95, evidence_ids=[], rejected_alternatives=[]
    )
    mock_verify.return_value = (False, {"availability": 0.0})
    target = healthy_baseline

    httpx.post(f"{BASE}/inject/F01", timeout=5)
    breach = detect_breach(target)
    assert breach is not None

    scenario = build_incident_scenario(target, breach, scenario_id="inc-live-unwind")
    result = build_workflow().invoke(
        IncidentState(
            incident_id="inc-live-unwind",
            scenario=scenario,
            mode="AUTONOMOUS",
            simulation_state={},
        )
    )

    assert result["outcome"] == "ESCALATED"
    assert read_value(
        (target.manifest.reversible_state or {})["model_selection"]
    ) == "primary", "unwind must restore the witnessed prior model"


def test_unwind_restores_after_direct_execute(target) -> None:
    """The executor's undo stack, exercised without the graph around it."""
    action = Action(
        name="switch_model",
        params={"target": "model_backup", "fallback": "model_primary"},
    )
    scenario = build_incident_scenario(
        target, _breach_for(target), scenario_id="inc-direct"
    )
    state = IncidentState(
        incident_id="inc-direct",
        scenario=scenario,
        mode="AUTONOMOUS",
        approved_actions=[action],
        simulation_state={},
    )

    res = execute_node(state)
    assert read_value((target.manifest.reversible_state or {})["model_selection"]) == "backup"

    state["undo_stack"] = res["undo_stack"]
    unwind_node(state)
    assert read_value((target.manifest.reversible_state or {})["model_selection"]) == "primary"


def _breach_for(target):
    httpx.post(f"{BASE}/inject/F01", timeout=5)
    breach = detect_breach(target)
    assert breach is not None
    return breach


# --- remediation debt against the live application ---


def test_debt_repayment_writes_to_the_live_app(healthy_baseline, proof2_app) -> None:
    """Repayment must move the real application, not a simulated dict."""
    from kavach.debt.repayment import repay_debt

    target = healthy_baseline
    scenario = build_incident_scenario(target, _breach_for(target), scenario_id="inc-repay")
    # outcome_node stamps the diagnosed class onto the scenario before debt is
    # recorded, so the checker only ever repays a classified incident. Detection
    # leaves it UNKNOWN, and repaying an unclassified incident is refused -- see
    # test_repayment_of_an_unclassified_incident_is_refused.
    scenario.fault_class = "F01"
    rs_def = (target.manifest.reversible_state or {})["model_selection"]

    # Mitigate: move onto the backup, as the F01 repair does.
    effect = load_catalogue().actions["switch_model"].effect
    assert effect is not None
    apply_effect(
        effect,
        Action(name="switch_model", params={"target": "model_backup"}),
        rs_def,
        mode="AUTONOMOUS",
    )
    assert read_value(rs_def) == "backup"

    # Primary recovers, then the debt is repaid.
    httpx.post(f"{BASE}/revert/F01", timeout=5)
    ok = repay_debt(
        scenario,
        {},
        "switch_model",
        {"target": "model_primary", "fallback": "model_backup"},
        mode="AUTONOMOUS",
    )

    assert ok is True
    assert read_value(rs_def) == "primary", "repayment must return the live app to primary"


def test_repayment_of_an_unclassified_incident_is_refused(healthy_baseline, proof2_app) -> None:
    """The deny case: no known risk tier means no autonomous repayment.

    An unclassified incident has no catalogue entry, so its risk tier is unknown.
    Absent information is not permission: the repayment is refused and the
    application is left where it was rather than written to on a guess.
    """
    from kavach.debt.repayment import repay_debt

    target = healthy_baseline
    scenario = build_incident_scenario(target, _breach_for(target), scenario_id="inc-unk")
    assert scenario.fault_class == "UNKNOWN"
    rs_def = (target.manifest.reversible_state or {})["model_selection"]

    # Put it in the mitigated position first, so "nothing moved" is a real
    # assertion rather than the state it already happened to be in.
    httpx.post(f"{BASE}/v1/admin/model", json={"model": "backup"}, timeout=5)
    httpx.post(f"{BASE}/revert/F01", timeout=5)

    ok = repay_debt(
        scenario,
        {},
        "switch_model",
        {"target": "model_primary", "fallback": "model_backup"},
        mode="AUTONOMOUS",
    )

    assert ok is False
    assert read_value(rs_def) == "backup", "a refused repayment must write nothing"


# --- the detection tick, which is what makes a heal start with no human ---


def test_detection_tick_opens_one_incident_per_breach(proof2_app) -> None:
    """The tick decides whether to open an incident; the graph is covered above."""
    from kavach.api.store import INCIDENTS_STORE
    from kavach.config import settings
    from kavach.detection.loop import detection_tick

    async def _noop_graph(incident_id, initial_state):
        return None

    INCIDENTS_STORE.clear()
    original = settings.target_manifest
    settings.target_manifest = str(MANIFEST)
    try:
        with patch(
            "kavach.api.routes.incidents.execute_graph_background", _noop_graph
        ):
            assert asyncio.run(detection_tick()) is None, "healthy app, no incident"

            httpx.post(f"{BASE}/inject/F01", timeout=5)
            incident_id = asyncio.run(detection_tick())
            assert incident_id is not None
            assert INCIDENTS_STORE[incident_id]["scenario"].target is not None
            assert INCIDENTS_STORE[incident_id]["mode"] == settings.execution_mode

            # The 15s tick must not open a second incident for a fault the first
            # is still handling; two would race for the same writer lock.
            assert asyncio.run(detection_tick()) is None
    finally:
        settings.target_manifest = original
        INCIDENTS_STORE.clear()

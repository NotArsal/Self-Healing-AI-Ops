from typing import Any

import pytest

from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.scenarios.loader import load_scenario


def mock_rca_factory(monkeypatch: pytest.MonkeyPatch, fault_class: str) -> None:
    def fake_analyze(*args: Any, **kwargs: Any) -> RCAResponse:
        return RCAResponse(
            fault_class=fault_class,
            confidence=0.9,
            evidence_ids=[],
            rejected_alternatives=[],
        )

    monkeypatch.setattr("kavach.graph.nodes.analyze_root_cause", fake_analyze)


def test_f06_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rca_factory(monkeypatch, "F06")
    scenario = load_scenario("F06")
    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }
    result = app.invoke(initial_state)

    assert result["verification_passed"] is True
    assert result["outcome"] == "MITIGATED"
    assert result["approved_actions"][0].name == "scale_retrievers"


def test_f08_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rca_factory(monkeypatch, "F08")
    scenario = load_scenario("F08")
    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }
    result = app.invoke(initial_state)

    assert result["verification_passed"] is True
    assert result["outcome"] == "MITIGATED"
    assert result["approved_actions"][0].name == "rollback_config"


def test_f09_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rca_factory(monkeypatch, "F09")
    scenario = load_scenario("F09")
    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }
    result = app.invoke(initial_state)

    assert result["verification_passed"] is True
    assert result["outcome"] == "MITIGATED"
    assert result["approved_actions"][0].name == "enable_token_limiter"

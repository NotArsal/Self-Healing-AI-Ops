"""Manifest validation tests.

Every test here is a deny case. The validators exist to refuse manifests that
would let a project reach ARMED while describing something Kavach cannot
safely operate, so proving they accept a good manifest is not enough.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from kavach.onboarding.manifest import Manifest, load

TARGET_MANIFEST = Path(r"D:\Vit\Academics Sem-5\EDI\Target_RAG-App\kavach.yaml")


# Any is right here: this builds arbitrary YAML-shaped fixture data that the
# tests then deliberately corrupt. It is not a module boundary.
def _good() -> dict[str, Any]:
    return {
        "apiVersion": "kavach/v1",
        "project": {
            "name": "t",
            "compose_file": "./docker-compose.yml",
            "compose_project": "t_proj",
            "git": {"base_branch": "dev", "ops_branch": "kavach/ops", "push": False,
                    "protected_branches": ["main"]},
        },
        "services": {"api": {"role": "application", "health": "http://x/healthz"}},
        "slo": [{"name": "s", "expression": "up", "comparator": "<",
                 "threshold": 1.0, "window_s": 60}],
        "verification": {"fast": {"set": "kavach/verification/fast_set.yaml"}},
        "denied_mutations": ["embed_model_change", "data_delete", "database_drop",
                             "scale_to_zero", "migration"],
    }


def test_good_manifest_validates() -> None:
    m = Manifest.model_validate(_good())
    assert m.mode == "SIMULATION", "omitting mode must mean SIMULATION"


def test_push_true_is_rejected() -> None:
    d = _good()
    d["project"]["git"]["push"] = True
    with pytest.raises(ValueError, match="never pushes"):
        Manifest.model_validate(d)


def test_ops_branch_must_be_namespaced() -> None:
    d = _good()
    d["project"]["git"]["ops_branch"] = "main"
    with pytest.raises(ValueError, match="kavach/ namespace"):
        Manifest.model_validate(d)


def test_blank_ownership_key_is_rejected() -> None:
    d = _good()
    d["project"]["compose_project"] = "   "
    with pytest.raises(ValueError, match="ownership key"):
        Manifest.model_validate(d)


def test_fake_quantile_label_is_rejected() -> None:
    """The exact mistake the first draft of the spec made."""
    d = _good()
    d["slo"][0]["expression"] = 'http_request_duration_seconds{quantile="0.95"}'
    with pytest.raises(ValueError, match="histogram_quantile"):
        Manifest.model_validate(d)


def test_numeric_status_regex_is_rejected() -> None:
    """status is bucketed 2xx/4xx/5xx, so status=~"5.." matches nothing."""
    d = _good()
    d["slo"][0]["expression"] = 'rate(http_requests_total{status=~"5.."}[5m])'
    with pytest.raises(ValueError, match='status="5xx"'):
        Manifest.model_validate(d)


def test_no_slo_is_rejected() -> None:
    d = _good()
    d["slo"] = []
    with pytest.raises(ValueError, match="at least one SLO"):
        Manifest.model_validate(d)


def test_duplicate_slo_names_rejected() -> None:
    d = _good()
    d["slo"].append(dict(d["slo"][0]))
    with pytest.raises(ValueError, match="duplicate SLO names"):
        Manifest.model_validate(d)


def test_incomplete_deny_list_is_rejected() -> None:
    d = _good()
    d["denied_mutations"] = ["data_delete"]
    with pytest.raises(ValueError, match="embed_model_change"):
        Manifest.model_validate(d)


def test_denied_action_cannot_be_allow_listed() -> None:
    d = _good()
    d["allowed_actions"] = ["restart_container", "database_drop"]
    with pytest.raises(ValueError, match="denied mutations"):
        Manifest.model_validate(d)


def test_embed_model_cannot_be_settable() -> None:
    """A settable embed_model is a settable corpus deletion."""
    d = _good()
    d["control_interface"] = {
        "config": "http://x/v1/admin/config", "auth": "header:X-Admin-Token",
        "auth_env": "KAVACH_ADMIN_TOKEN", "settable": ["llm_model", "embed_model"],
    }
    with pytest.raises(ValueError, match="embed_model must never be settable"):
        Manifest.model_validate(d)


def test_control_plane_path_must_bypass_the_proxy() -> None:
    d = _good()
    d["llm"] = {
        "provider": "ollama", "model": "m", "embedding_model": "e",
        "paths": {"primary": "http://toxiproxy:21434", "backup": None},
        "control_plane_path": "http://toxiproxy:21434",
    }
    with pytest.raises(ValueError, match="blind the diagnostician"):
        Manifest.model_validate(d)


def test_verification_budget_must_fit_the_loop() -> None:
    d = _good()
    d["verification"]["fast"]["max_duration_s"] = 600
    with pytest.raises(ValueError, match="between 10 and 150"):
        Manifest.model_validate(d)


def test_unknown_key_is_rejected() -> None:
    """extra="forbid" everywhere: a typo must not be silently ignored."""
    d = _good()
    d["projekt"] = {}
    with pytest.raises(ValueError):
        Manifest.model_validate(d)


@pytest.mark.skipif(not TARGET_MANIFEST.is_file(), reason="target repo not present")
def test_real_target_manifest_validates() -> None:
    """The manifest actually shipped in the target must pass."""
    m = load(TARGET_MANIFEST)
    assert m.project.compose_project == "target_rag-app"
    assert m.project.git.base_branch == "modernize-stack"
    assert m.project.git.push is False
    assert m.mode == "SIMULATION"
    assert m.allowed_actions == [], "allow-list must ship empty"
    assert m.verification.fast.max_duration_s == 120
    assert len(m.slo) >= 1
    # Every expression must look like PromQL, not a bare metric name.
    for slo in m.slo:
        assert any(c in slo.expression for c in "()[]"), slo.name


@pytest.mark.skipif(not TARGET_MANIFEST.is_file(), reason="target repo not present")
def test_real_manifest_round_trips_as_yaml() -> None:
    raw = yaml.safe_load(TARGET_MANIFEST.read_text(encoding="utf-8"))
    assert Manifest.model_validate(raw).project.name == "simple-rag"

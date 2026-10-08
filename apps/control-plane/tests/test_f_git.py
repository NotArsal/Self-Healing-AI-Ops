import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch
from kavach.scenarios.schema import Scenario, ServiceDef, PermissionDef
from kavach.tnr.models import Action
from kavach.graph.state import IncidentState
from kavach.graph.nodes import execute_node, unwind_node

def test_gitops_adapter_and_f07():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Init git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
        
        prompt_file = tmp_path / "prompts.yaml"
        prompt_file.write_text("version: v1\n")
        subprocess.run(["git", "add", "prompts.yaml"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)
        
        # We need to monkeypatch cwd so the execute_node runs in tmpdir
        cwd_before = os.getcwd()
        os.environ["KAVACH_CATALOGUE_DIR"] = str(Path(cwd_before) / "catalogue_data")
        os.chdir(tmp_path)
        try:
            scenario = Scenario(
                id="test-git",
                fault_class="F07",
                services={"web": ServiceDef(role="application")},
                permissions=PermissionDef(allowed_actions=["rollback_prompt"], max_risk_tier="HIGH"),
                health={},
                evidence=[]
            )
            
            action = Action(name="rollback_prompt", params={"target_version": "last_known_good"})
            state = IncidentState(
                incident_id="inc-123",
                scenario=scenario,
                mode="LIVE",
                approved_actions=[action],
                simulation_state={"prompt_version": "v1"}
            )
            
            # Execute
            res = execute_node(state)
            
            # Assert ops branch created
            res_branch = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True)
            assert res_branch.stdout.strip() == "kavach/ops"
            
            # Assert file is modified
            assert prompt_file.read_text() == "version: last_known_good\n"
            
            # Unwind
            state["undo_stack"] = res["undo_stack"]
            state["simulation_state"] = res["simulation_state"]
            unwind_res = unwind_node(state)
            
            # Assert file is rolled back
            assert prompt_file.read_text() == "version: v1\n"
            
            # Assert commit history has the undo
            log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True)
            assert "Undo rollback_prompt" in log.stdout
            assert "Execute rollback_prompt to last_known_good" in log.stdout
            
        finally:
            os.chdir(cwd_before)

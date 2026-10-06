import tempfile
from pathlib import Path

import pytest

from kavach.catalogue.loader import (
    CatalogueValidationError,
    load_catalogue,
    reset_catalogue,
)


def test_missing_inverse_throws_error() -> None:
    reset_catalogue()
    
    # We will create a temporary yaml file with a missing inverse
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_yaml = """
        actions:
          - name: bad_action
            inverse:
              name: missing_inverse_action
              params_mapping: {}
            mutations: {}
        """
        
        path = Path(tmpdir) / "bad.yaml"
        path.write_text(bad_yaml)
        
        with pytest.raises(CatalogueValidationError) as exc_info:
            load_catalogue(base_dir=str(tmpdir))
            
        assert "not defined in the catalogue" in str(exc_info.value)
        
    reset_catalogue()


def test_dynamic_f99_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_catalogue()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create F99 scenario and actions catalogue
        f99_yaml = """
        actions:
          - name: restart_cache
            inverse:
              name: stop_cache
              params_mapping: {}
            mutations:
              cache: "healthy"
              
          - name: stop_cache
            inverse:
              name: noop
              params_mapping: {}
            mutations:
              cache: "unavailable"
              
          - name: noop
            inverse:
              name: noop
              params_mapping: {}
            mutations: {}

        faults:
          - fault_class: F99
            recommended_actions:
              - restart_cache
        """
        path = Path(tmpdir) / "f99_cat.yaml"
        path.write_text(f99_yaml)
        
        # We need to monkeypatch the catalogue directory so load_catalogue reads from here
        def fake_load_catalogue(base_dir="catalogue_data"):
            return load_catalogue(base_dir=str(tmpdir))
            
        monkeypatch.setattr("kavach.graph.nodes.load_catalogue", fake_load_catalogue)
        monkeypatch.setattr("kavach.simulation.executor.load_catalogue", fake_load_catalogue)
        
        # Let's run a manual execution using the executor directly, 
        # because the graph relies on scenario.yaml definitions (F99 doesn't exist in scenarios/ dir)
        # We can just test the executor logic
        from kavach.simulation.executor import execute_action
        from kavach.tnr.models import Action
        
        action = Action(name="restart_cache", params={})
        state = {"cache": "degraded"}
        
        undo_record = execute_action(action, state)
        
        assert state["cache"] == "healthy"
        assert undo_record.inverse_action.name == "stop_cache"
        assert undo_record.pre_state_witness["cache"] == "degraded"
        
        # Test applying inverse manually
        execute_action(undo_record.inverse_action, state)
        assert state["cache"] == "unavailable"
        
    reset_catalogue()

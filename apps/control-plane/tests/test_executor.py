from unittest.mock import patch

import pytest

from kavach.remediation.executor import RequiresHumanApprovalError, execute_command
from kavach.remediation.tnr_gate import SafetyAssessment


@patch("kavach.remediation.executor.evaluate_safety")
def test_execute_safe_command(mock_evaluate):
    # Mock TNR gate to approve
    mock_evaluate.return_value = SafetyAssessment(is_safe=True, reason="Safe")
    
    success, output = execute_command("echo 'hello'", "Context")
    
    assert success is True
    assert "hello" in output
    mock_evaluate.assert_called_once_with("echo 'hello'", "Context")

@patch("kavach.remediation.executor.evaluate_safety")
def test_execute_unsafe_command_raises(mock_evaluate):
    # Mock TNR gate to deny
    mock_evaluate.return_value = SafetyAssessment(is_safe=False, reason="Destructive command")
    
    with pytest.raises(RequiresHumanApprovalError) as exc_info:
        execute_command("rm -rf /", "Context")
        
    assert exc_info.value.command == "rm -rf /"
    assert "Destructive command" in str(exc_info.value)
